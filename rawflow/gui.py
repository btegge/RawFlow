"""Local Tk desktop interface for the existing evidence-gated RAW pipeline."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from .presets import LABELS, draft_preview
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageOps, ImageTk, ImageCms
from .core import locate
from .gui_jobs import BatchOptions, run_batch, completed_results

PROJECT = Path(__file__).resolve().parents[1]
def configure_tools():
    # Optional machine-local paths stay outside version control.
    try:
        defaults=json.loads((PROJECT/'work/local-tools.json').read_text())
    except (OSError,ValueError):
        defaults={}
    for key in ('RAWFLOW_RAWTHERAPEE_CLI','RAWFLOW_DARKTABLE_CLI','RAWFLOW_EXIFTOOL'):
        path=defaults.get(key)
        if key not in os.environ and isinstance(path,str) and Path(path).is_file():
            os.environ[key]=path


def load_image(path):
    with Image.open(path) as source:
        source.draft('RGB', (1800, 1400))
        image = ImageOps.exif_transpose(source).convert('RGB')
        if source.info.get('icc_profile'):
            image = ImageCms.profileToProfile(image,
                ImageCms.ImageCmsProfile(io.BytesIO(source.info['icc_profile'])),
                ImageCms.createProfile('sRGB'), outputMode='RGB', renderingIntent=1)
        image.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
        return image.copy()


def camera_preview(path):
    path = Path(path)
    st = path.stat()
    return _camera_preview(str(path), st.st_size, st.st_mtime_ns)


@lru_cache(maxsize=12)
def _camera_preview(path, size, modified):
    exe = locate('exiftool')
    if not exe:
        raise RuntimeError('Camera preview needs ExifTool. Set its location in Setup.')
    for tag in ('JpgFromRaw', 'PreviewImage'):
        result = subprocess.run([exe, '-b', '-' + tag, str(path)], capture_output=True, timeout=30)
        if result.returncode == 0 and result.stdout:
            return load_image(io.BytesIO(result.stdout))
    raise ValueError('This photo has no available camera preview. Its RAW export may still work.')


class PhotoView(ttk.Frame):
    def __init__(self, master, title):
        super().__init__(master, style='Card.TFrame', padding=12)
        self.caption = tk.StringVar(value=title)
        ttk.Label(self, textvariable=self.caption, style='CardTitle.TLabel').pack(anchor='w', pady=(0, 10))
        self.canvas = tk.Canvas(self, bg='#111827', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.source = self.photo = None
        self.placeholder = 'Choose a photo to see its preview'
        self.canvas.bind('<Configure>', self.redraw)
    def show(self, source, caption):
        self.source = source
        self.caption.set(caption)
        self.redraw()
    def clear(self, text):
        self.source = self.photo = None
        self.placeholder = text
        self.redraw()
    def redraw(self, event=None):
        self.canvas.delete('all')
        w, h = max(self.canvas.winfo_width(), 2), max(self.canvas.winfo_height(), 2)
        if self.source:
            image = self.source.copy()
            image.thumbnail((w, h), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(image, master=self.canvas)
            self.canvas.create_image(w//2, h//2, image=self.photo, anchor='center')
        else:
            self.canvas.create_text(w//2, h//2, text=self.placeholder, fill='#94a3b8', width=max(40, w-30), font=('Helvetica', 13))


class RawFlowApp:
    def __init__(self, root):
        self.root = root
        root.title('RawFlow — Photo Editor')
        root.geometry('1360x900')
        root.minsize(1100, 820)
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.entries = {}
        self.selected_path = None
        self.preview_token = 0
        self.preview_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview")
        self.preview_future = None
        self.last_folder = None
        self.project = PROJECT
        self.base = PROJECT/'profiles/neutral-rt5.13.pp3'
        self.evidence = PROJECT/'validation/backend-evidence.json'
        self.output = tk.StringVar(value=str(PROJECT/'outputs/desktop'))
        self.look = tk.StringVar(value='Punchy')
        self.strength = tk.StringVar(value='Low')
        self.scene = tk.StringVar(value='Preserve the scene')
        self.wb = tk.StringVar(value='Camera white balance')
        self.status = tk.StringVar(value='Add photos or open a previous batch to begin.')
        self.details = tk.StringVar(value='Original photos stay untouched. Only final JPEGs are saved to your output folder.')
        self.preferences = PROJECT/'work/desktop-settings.json'
        self.restore_preferences()
        self.setup_window = None
        self.closing = False
        self.build()
        root.protocol('WM_DELETE_WINDOW', self.close)
        if root.tk.call('tk', 'windowingsystem') == 'aqua':
            root.createcommand('::tk::mac::Quit', self.close)
        root.after(100, self.drain)

    def restore_preferences(self):
        try:
            data=json.loads(self.preferences.read_text())
            self.base=Path(data.get('base',self.base));self.evidence=Path(data.get('evidence',self.evidence))
            for key,var,allowed in [('strength',self.strength,('Low','Medium','High')),('look',self.look,tuple(LABELS)),('scene',self.scene,('Preserve the scene','Brighten toward daylight')),('wb',self.wb,('Camera white balance','Find neutral colors'))]:
                if data.get(key) in allowed:var.set(data[key])
            if isinstance(data.get('output'),str):self.output.set(data['output'])
            for key in ('RAWFLOW_RAWTHERAPEE_CLI','RAWFLOW_EXIFTOOL'):
                if isinstance(data.get(key),str):os.environ[key]=data[key]
        except (OSError,ValueError,TypeError):pass

    def save_preferences(self):
        data={'base':str(self.base),'evidence':str(self.evidence),'output':self.output.get(),
              'look':self.look.get(),'strength':self.strength.get(),'scene':self.scene.get(),'wb':self.wb.get()}
        for key in ('RAWFLOW_RAWTHERAPEE_CLI','RAWFLOW_EXIFTOOL'):
            if key in os.environ:data[key]=os.environ[key]
        try:
            self.preferences.parent.mkdir(parents=True,exist_ok=True)
            self.preferences.write_text(json.dumps(data,indent=2)+'\n')
        except OSError:
            # A read-only project can still edit to a user-selected destination.
            pass

    def build(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=('Helvetica', 12), background='#0b1220', foreground='#e5edf8')
        style.configure('Title.TLabel', font=('Helvetica', 25, 'bold'))
        style.configure('Subtitle.TLabel', foreground='#94a3b8')
        style.configure('Card.TFrame', background='#172033')
        style.configure('CardTitle.TLabel', background='#172033', font=('Helvetica', 12, 'bold'))
        style.configure('TButton', padding=(12, 9), borderwidth=0, relief='flat', background='#243247', foreground='#e5edf8')
        style.map('TButton',background=[('active','#33465e')])
        for name in ('TEntry','TCombobox','Treeview','Treeview.Heading','Vertical.TScrollbar','Horizontal.TProgressbar'):
            style.configure(name,bordercolor='#263349',lightcolor='#263349',darkcolor='#263349',borderwidth=0,relief='flat')
        style.configure('Vertical.TScrollbar',background='#334155',troughcolor='#172033',arrowcolor='#94a3b8',arrowsize=12)
        style.map('Vertical.TScrollbar',background=[('active','#475569')])
        style.map('TEntry',bordercolor=[('focus','#3b5678')],lightcolor=[('focus','#3b5678')],darkcolor=[('focus','#3b5678')])
        style.configure('TEntry',fieldbackground='#172033',foreground='#e5edf8',insertcolor='#e5edf8',padding=8)
        style.configure('TCombobox',fieldbackground='#172033',foreground='#e5edf8',arrowcolor='#e5edf8',padding=6)
        style.map('TCombobox',fieldbackground=[('readonly','#172033')],foreground=[('readonly','#e5edf8')])
        style.configure('Horizontal.TProgressbar',background='#60a5fa',troughcolor='#172033',borderwidth=0)
        style.configure('Treeview.Heading',background='#243247',foreground='#94a3b8',padding=8)
        style.map('Treeview',background=[('selected','#234671')],foreground=[('selected','#ffffff')])
        style.layout('Preset.TRadiobutton',style.layout('Toolbutton'))
        style.configure('Preset.TRadiobutton',background='#172033',foreground='#94a3b8',padding=(10,6),borderwidth=0)
        style.map('Preset.TRadiobutton',background=[('selected','#2563eb'),('active','#243247')],foreground=[('selected','#ffffff')])
        style.configure('Accent.TButton', background='#2563eb', foreground='#ffffff', font=('Helvetica', 12, 'bold'))
        style.map('Accent.TButton', background=[('disabled','#a5b4ce'),('active','#1d4ed8')])
        style.configure('Treeview', rowheight=34, fieldbackground='#172033', background='#172033')
        style.configure('Treeview.Heading', font=('Helvetica', 11, 'bold'))
        self.root.configure(bg='#0b1220')
        shell = ttk.Frame(self.root, padding=20); shell.pack(fill='both', expand=True)
        shell.columnconfigure(0,weight=1);shell.rowconfigure(2,weight=1)
        header = ttk.Frame(shell); header.grid(row=0,column=0,sticky='ew',pady=(0,16))
        icon_path=PROJECT/'RawFlow.app/Contents/Resources/RawFlow.icns'
        if icon_path.is_file():
            with Image.open(icon_path) as icon:
                self.brand_icon=ImageTk.PhotoImage(icon.convert('RGBA').resize((48,48),Image.Resampling.LANCZOS),master=self.root)
            ttk.Label(header,image=self.brand_icon).pack(side='left',padx=(0,12))
            self.root.iconphoto(True,self.brand_icon)
            def set_mac_icon():
                if self.root.tk.call('tk','windowingsystem') == 'aqua':
                    import ctypes
                    try:
                        native=ctypes.CDLL(None).RawFlowSetApplicationIcon
                        native.argtypes=[ctypes.c_char_p];native.restype=None
                        native(os.fsencode(icon_path))
                    except AttributeError:
                        pass  # Direct Python launches use Tk's iconphoto fallback.
            self.root.after_idle(set_mac_icon)
        ttk.Label(header,text='RawFlow',style='Title.TLabel').pack(side='left')
        ttk.Label(header,text='PHOTO STUDIO  /  LOCAL RAW',style='Subtitle.TLabel').pack(side='left',padx=16)
        ttk.Button(header,text='Setup',command=self.setup).pack(side='right')
        ttk.Button(header,text='Open batch…',command=self.open_batch).pack(side='right',padx=8)
        toolbar=ttk.Frame(shell);toolbar.grid(row=1,column=0,sticky='ew',pady=(0,16))
        self.add_button=ttk.Button(toolbar,text='Add photos…',command=self.add_files);self.add_button.pack(side='left')
        self.folder_button=ttk.Button(toolbar,text='Add folder…',command=self.add_folder);self.folder_button.pack(side='left',padx=8)
        self.remove_button=ttk.Button(toolbar,text='Remove selected',command=self.remove);self.remove_button.pack(side='left')
        self.reveal_button=ttk.Button(toolbar,text='Show exports',command=self.reveal,state='disabled');self.reveal_button.pack(side='right')
        content=ttk.Panedwindow(shell,orient='horizontal');content.grid(row=2,column=0,sticky='nsew')
        side=ttk.Frame(content,width=290,padding=(0,0,14,0));content.add(side,weight=0)
        side.columnconfigure(0,weight=1);side.rowconfigure(1,weight=1)
        ttk.Label(side,text='PHOTOS',style='Subtitle.TLabel').grid(row=0,column=0,sticky='w',pady=(0,8))
        self.tree=ttk.Treeview(side,columns=('status',),selectmode='extended',height=8)
        self.tree.heading('#0',text='Photo');self.tree.heading('status',text='Status')
        self.tree.column('#0',width=165,minwidth=120);self.tree.column('status',width=80,minwidth=65)
        scroll=ttk.Scrollbar(side,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1,column=1,sticky='ns');self.tree.grid(row=1,column=0,sticky='nsew')
        self.tree.bind('<<TreeviewSelect>>',self.selection)
        controls=ttk.Frame(side,padding=(0,16,0,0));controls.grid(row=2,column=0,sticky='ew')
        self.option_widgets=[]
        self.preset_buttons=[]
        ttk.Label(controls,text='LOOK',style='Subtitle.TLabel').pack(anchor='w',pady=(8,4))
        presets=ttk.Frame(controls);presets.pack(fill='x')
        for i,label in enumerate(LABELS):
            button=ttk.Radiobutton(presets,text=label,variable=self.look,value=label,style='Preset.TRadiobutton',
                command=lambda:self.selection(force_draft=True))
            button.grid(row=i//2,column=i%2,sticky='ew',padx=(0,8),pady=2)
            self.preset_buttons.append(button)
        ttk.Label(controls,text='STRENGTH',style='Subtitle.TLabel').pack(anchor='w',pady=(10,5))
        levels=ttk.Frame(controls);levels.pack(fill='x')
        for i,label in enumerate(('Low','Medium','High')):
            levels.columnconfigure(i,weight=1)
            button=ttk.Radiobutton(levels,text=label,variable=self.strength,value=label,style='Preset.TRadiobutton',command=lambda:self.selection(force_draft=True))
            button.grid(row=0,column=i,sticky='ew',padx=2)
            self.preset_buttons.append(button)
        for label,var,choices in [
            ('BRIGHTNESS',self.scene,['Preserve the scene','Brighten toward daylight']),
            ('WHITE BALANCE',self.wb,['Camera white balance','Find neutral colors'])]:
            ttk.Label(controls,text=label,style='Subtitle.TLabel').pack(anchor='w',pady=(8,4))
            box=ttk.Combobox(controls,textvariable=var,values=choices,state='readonly');box.pack(fill='x')
            self.option_widgets.append(box)
            box.bind('<<ComboboxSelected>>', lambda event: self.selection(force_draft=True))
        ttk.Label(controls,text='Strength: 100% / 125% / 150%',style='Subtitle.TLabel',wraplength=270).pack(anchor='w',pady=(14,8))
        viewers=ttk.Frame(content);content.add(viewers,weight=1)
        viewers.columnconfigure(0,weight=1,uniform='preview');viewers.columnconfigure(1,weight=1,uniform='preview');viewers.rowconfigure(0,weight=1)
        self.before=PhotoView(viewers,'Before');self.before.grid(row=0,column=0,sticky='nsew',padx=(0,7))
        self.after=PhotoView(viewers,'After');self.after.grid(row=0,column=1,sticky='nsew',padx=(7,0))
        ttk.Label(shell,textvariable=self.details,style='Subtitle.TLabel',wraplength=1150).grid(row=3,column=0,sticky='w',pady=(12,12))
        dest=ttk.Frame(shell);dest.grid(row=4,column=0,sticky='ew',pady=(0,12))
        ttk.Label(dest,text='Save edits in',style='Subtitle.TLabel').pack(side='left',padx=(0,12))
        self.output_entry=ttk.Entry(dest,textvariable=self.output);self.output_entry.pack(side='left',fill='x',expand=True)
        self.output_button=ttk.Button(dest,text='Choose…',command=self.choose_output);self.output_button.pack(side='left',padx=(8,0))
        bottom=ttk.Frame(shell);bottom.grid(row=5,column=0,sticky='ew')
        self.start_button=ttk.Button(bottom,text='Edit all photos',style='Accent.TButton',command=self.start);self.start_button.pack(side='right')
        self.stop_button=ttk.Button(bottom,text='Stop after this photo',command=self.request_stop,state='disabled');self.stop_button.pack(side='right',padx=8)
        ttk.Label(bottom,textvariable=self.status,wraplength=680).pack(side='left',fill='x',expand=True)
        self.progress=ttk.Progressbar(shell,mode='determinate',maximum=100);self.progress.grid(row=6,column=0,sticky='ew',pady=(12,0))
        menu=tk.Menu(self.root);filemenu=tk.Menu(menu,tearoff=False)
        filemenu.add_command(label='Add photos…',command=self.add_files,accelerator='⌘O')
        filemenu.add_command(label='Open batch…',command=self.open_batch)
        filemenu.add_command(label='Edit all photos',command=self.start,accelerator='⌘Return')
        filemenu.add_separator();filemenu.add_command(label='Quit',command=self.close)
        menu.add_cascade(label='File',menu=filemenu);self.root.config(menu=menu)
        self.root.bind('<Command-o>',lambda e:self.add_files())
        self.root.bind('<Command-Return>',lambda e:self.start())
        self.root.bind('<Command-O>',lambda e:self.open_batch())
        self.root.bind('<Command-comma>',lambda e:self.setup())
        self.root.bind('<Command-q>',lambda e:self.close())

    def add_paths(self, paths, select=True):
        if self.busy: return
        for path in paths:
            path=Path(path).resolve()
            if path.suffix.lower()!='.cr3' or not path.is_file() or path in self.entries: continue
            key=self.tree.insert('', 'end',text=path.name,values=('Ready',))
            self.entries[path]={'key':key,'output':None,'error':None}
        if self.entries and select:
            first=next(iter(self.entries.values()))['key'];self.tree.selection_set(first)
        self.status.set(f'{len(self.entries)} photos in the queue.')

    def add_files(self):
        if not self.busy:
            self.add_paths(filedialog.askopenfilenames(parent=self.root,title='Choose Canon RAW photos',filetypes=[('Canon RAW photos','*.CR3 *.cr3'),('All files','*')]))
    def add_folder(self):
        if self.busy:return
        folder=filedialog.askdirectory(parent=self.root,title='Choose a photo folder')
        if folder:self.add_paths(sorted(p for p in Path(folder).iterdir() if p.suffix.lower()=='.cr3'))
    def remove(self):
        if self.busy:return
        keys=set(self.tree.selection())
        for path in list(self.entries):
            if self.entries[path]['key'] in keys:
                self.tree.delete(self.entries[path]['key']);del self.entries[path]
        self.selection()
        self.status.set(f'{len(self.entries)} photos in the queue.')
    def choose_output(self):
        folder=filedialog.askdirectory(parent=self.root,title='Choose where to save edited photos')
        if folder:self.output.set(folder)

    def selection(self,event=None,force_draft=False):
        keys=self.tree.selection()
        self.preview_token+=1;token=self.preview_token
        if not keys:
            self.selected_path=None;self.before.clear('Choose a photo');self.after.clear('An edited photo will appear here');return
        path=next((p for p,e in self.entries.items() if e['key']==keys[0]),None)
        if path is None:return
        self.selected_path=path;entry=self.entries[path];output=entry['output']
        self.before.clear('Loading preview…');self.after.clear('Preparing draft preview…')
        if entry['error']:self.details.set(f'{path.name}: {entry["error"]}')
        else:self.details.set(path.name)
        look = LABELS[self.look.get()]
        strength = self.strength.get().lower()
        scene = 'normal' if self.scene.get() == 'Brighten toward daylight' else 'preserve'
        wb = 'neutral-search' if self.wb.get() == 'Find neutral colors' else 'camera'
        def worker():
            try:
                if output and not force_draft:
                    before_path=output/'baseline.jpg'
                    before=load_image(before_path) if before_path.exists() else camera_preview(path)
                    recipe=json.loads((output/'recipe.json').read_text());settings=recipe.get('settings',{})
                    after=load_image(Path(recipe.get('export_path',output/'export.jpg')))
                    self.events.put(('preview',token,before,after,'Before · neutral RAW' if before_path.exists() else 'Before · camera preview',settings))
                else:
                    before = camera_preview(path)
                    after = draft_preview(before, look, scene, wb, strength)
                    self.events.put(('draft', token, before, after, look+' · '+strength))
            except Exception as e:self.events.put(('preview_error',token,str(e)))
        if self.preview_future:
            self.preview_future.cancel()
        self.preview_future = self.preview_pool.submit(worker)

    def set_busy(self,busy):
        self.busy=busy
        for widget in (self.add_button,self.folder_button,self.remove_button,self.output_entry,self.output_button,self.start_button):
            widget.configure(state='disabled' if busy else 'normal')
        for box in self.option_widgets:box.configure(state='disabled' if busy else 'readonly')
        for button in self.preset_buttons:button.configure(state='disabled' if busy else 'normal')
        self.stop_button.configure(state='normal' if busy else 'disabled')

    def start(self):
        if self.busy:return
        paths=list(self.entries)
        if not paths:messagebox.showinfo('Add photos','Choose some CR3 photos first.',parent=self.root);return
        if not self.output.get().strip():messagebox.showerror('Choose a destination','Select a folder for your edits.',parent=self.root);return
        options=BatchOptions(self.base,self.evidence,Path(self.output.get()).expanduser().resolve(),
            LABELS[self.look.get()],
            'preserve' if self.scene.get()=='Preserve the scene' else 'normal',
            'camera' if self.wb.get()=='Camera white balance' else 'neutral-search', self.strength.get().lower())
        self.save_preferences()
        self.stop.clear();self.set_busy(True);self.progress.configure(value=0)
        self.status.set('Checking the processor and preparing this batch…')
        threading.Thread(target=run_batch,args=(paths,options,self.events,self.stop),daemon=True).start()

    def request_stop(self):
        self.stop.set();self.stop_button.configure(state='disabled');self.status.set('Stopping after the current photo is safely exported…')

    def drain(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event[0]
                if kind=='batch_folder':
                    self.last_folder=event[1];self.reveal_button.configure(state='normal')
                elif kind=='started':
                    _,path,index,total=event;self.tree.set(self.entries[path]['key'],'status','Editing')
                    self.progress.configure(value=100*index/total);self.status.set(f'{index+1} of {total} · {path.name}')
                elif kind=='progress':
                    _,path,label=event;self.status.set(f'{path.name} · {label}')
                elif kind=='edit_preview':
                    _,path,work=event
                    if path==self.selected_path:
                        token=self.preview_token
                        def load_edited(p=work, t=token):
                            try:
                                self.events.put(('rendered_preview', t, load_image(p/'baseline.jpg'), load_image(p/'edited-preview.jpg')))
                            except Exception as e:
                                self.events.put(('preview_error', t, str(e)))
                        self.preview_pool.submit(load_edited)
                elif kind=='draft' and event[1]==self.preview_token:
                    _,_,before,after,look=event
                    self.before.show(before,'Before · camera preview')
                    self.after.show(after,'Draft · '+look.replace('-', ' ').title())
                    self.details.set('Fast approximate preview from the camera JPEG. RAW processing may change brightness, color, and recovered detail.')
                elif kind=='rendered_preview' and event[1]==self.preview_token:
                    self.before.show(event[2],'Before · neutral RAW')
                    self.after.show(event[3],'After · RAW preview')
                    self.details.set('RAW preview ready. Saving the full-resolution JPEG…')
                elif kind=='completed':
                    _,path,output=event;self.entries[path].update(output=output,error=None)
                    self.tree.set(self.entries[path]['key'],'status','Done')
                    if path==self.selected_path:self.selection()
                elif kind=='failed':
                    _,path,error=event;self.entries[path]['error']=error
                    self.tree.set(self.entries[path]['key'],'status','Failed')
                    if path==self.selected_path:self.details.set(f'{path.name}: {error}')
                elif kind=='fatal':
                    self.status.set('The batch could not start.')
                    messagebox.showerror('Unable to start',event[1]+'\n\nUse Setup to check the processor, profile, and compatibility record.',parent=self.root)
                elif kind=='finished':
                    _,completed,failed,stopped,folder=event;self.set_busy(False)
                    if folder:
                        self.progress.configure(value=100 if not stopped else self.progress['value'])
                        self.status.set(f'{"Stopped" if stopped else "Finished"} · {completed} edited, {failed} failed. Originals unchanged.')
                elif kind=='preview' and event[1]==self.preview_token:
                    _,_,before,after,caption,settings=event;self.before.show(before,caption)
                    if after:self.after.show(after,'After · edited photo')
                    if settings:
                        self.details.set(f'{self.selected_path.name} · Exposure {settings.get("exposure",0):+.2f} EV · Contrast {settings.get("contrast",0):+g} · Color {settings.get("saturation",0):+g}')
                elif kind=='preview_error' and event[1]==self.preview_token:
                    self.before.clear('Preview unavailable');self.details.set(event[2])
                elif kind=='loaded_batch':
                    self.set_busy(False);self.apply_results(event[1],event[2])
                elif kind=='batch_load_error':
                    self.set_busy(False);messagebox.showerror('Unable to open batch',event[1],parent=self.root)
                elif kind=='validation_done':
                    self.evidence=event[1];self.save_preferences();self.set_busy(False);self.status.set('Compatibility check passed. Ready to edit.')
                    messagebox.showinfo('Ready to edit','The selected CR3 photo passed the processor and profile checks.',parent=self.root)
                elif kind=='validation_failed':
                    self.set_busy(False);self.status.set('Compatibility check failed.')
                    messagebox.showerror('Compatibility check failed',event[1],parent=self.root)
        except queue.Empty:pass
        if self.closing and not self.busy:
            self.preview_pool.shutdown(wait=False, cancel_futures=True)
            self.root.destroy();return
        self.root.after(100,self.drain)

    def open_batch(self):
        if self.busy:return
        folder=filedialog.askdirectory(parent=self.root,title='Choose an existing RawFlow output folder')
        if not folder:return
        def worker():
            try:
                results=completed_results(folder)
                self.events.put(('loaded_batch',Path(folder),results))
            except Exception as e:self.events.put(('batch_load_error',str(e)))
        self.set_busy(True);self.stop_button.configure(state='disabled');self.status.set('Opening completed edits…')
        threading.Thread(target=worker,daemon=True).start()

    def apply_results(self, folder, results):
        if not results:
            self.status.set('No completed edits found.')
            messagebox.showinfo('No finished edits','No completed RawFlow exports were found in that folder.',parent=self.root);return
        self.add_paths([path for path, _, _ in results], select=False)
        for path, output, data in results:
            self.entries[path].update(output=output,error=None)
            self.tree.set(self.entries[path]['key'],'status','Done')
        self.last_folder=Path(folder);self.reveal_button.configure(state='normal')
        self.tree.selection_set(self.entries[results[0][0]]['key'])
        self.selection();self.status.set(f'Opened {len(results)} completed edits.')

    def reveal(self):
        if self.selected_path and self.entries[self.selected_path]['output']:
            record=self.entries[self.selected_path]['output']
            try:
                target=Path(json.loads((record/'recipe.json').read_text()).get('export_path', str(record))).parent
            except (OSError, ValueError):
                target=self.last_folder
        else:target=self.last_folder
        if target:subprocess.Popen(['open',str(target)])

    def setup(self):
        if self.busy:return
        if self.setup_window and self.setup_window.winfo_exists():self.setup_window.lift();return
        win=tk.Toplevel(self.root);self.setup_window=win;win.title('RawFlow Setup');win.geometry('760x360');win.transient(self.root)
        frame=ttk.Frame(win,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Processing setup',font=('Helvetica',18,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,16))
        vars=[]
        values=[('RAW processor',locate('rawtherapee-cli') or ''),('Camera metadata tool',locate('exiftool') or ''),('Base editing profile',str(self.base)),('Compatibility record',str(self.evidence))]
        frame.columnconfigure(1,weight=1)
        for row,(label,value) in enumerate(values,1):
            var=tk.StringVar(value=value);vars.append(var)
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=8)
            ttk.Entry(frame,textvariable=var).grid(row=row,column=1,sticky='ew')
            def browse(v=var):
                path=filedialog.askopenfilename(parent=win)
                if path:v.set(path)
            ttk.Button(frame,text='Choose…',command=browse).grid(row=row,column=2,padx=(8,0))
        def apply():
            for v in vars:
                if not Path(v.get()).is_file():messagebox.showerror('File not found',v.get(),parent=win);return False
            os.environ['RAWFLOW_RAWTHERAPEE_CLI']=vars[0].get();os.environ['RAWFLOW_EXIFTOOL']=vars[1].get()
            self.base=Path(vars[2].get());self.evidence=Path(vars[3].get());return True
        def save():
            if apply():self.save_preferences();win.destroy()
        def validate():
            # A new record may be missing, so only validate the three input files.
            for v in vars[:3]:
                if not Path(v.get()).is_file():messagebox.showerror('File not found',v.get(),parent=win);return
            if not self.selected_path:messagebox.showinfo('Choose a sample','Add and select a CR3 photo first.',parent=win);return
            os.environ['RAWFLOW_RAWTHERAPEE_CLI']=vars[0].get();os.environ['RAWFLOW_EXIFTOOL']=vars[1].get();self.base=Path(vars[2].get())
            sample=self.selected_path;base=self.base;win.destroy();self.set_busy(True)
            self.stop_button.configure(state='disabled');self.status.set('Checking the sample photo. This can take a few minutes…')
            def worker():
                from .pipeline import spike
                try:
                    folder=PROJECT/'validation'/datetime.now().strftime('desktop-spike-%Y%m%d-%H%M%S-%f')
                    result=spike(sample,base,folder)
                    if result['rawtherapee']['status']!='passed':raise RuntimeError(result['rawtherapee'].get('error','One or more image checks failed. See '+str(folder)))
                    self.events.put(('validation_done',folder/'evidence.json'))
                except Exception as e:self.events.put(('validation_failed',str(e)))
            threading.Thread(target=worker,daemon=True).start()
        buttons=ttk.Frame(frame);buttons.grid(row=5,column=0,columnspan=3,sticky='ew',pady=(16,0))
        ttk.Button(buttons,text='Validate selected sample',command=validate).pack(side='left')
        ttk.Button(buttons,text='Save setup',command=save).pack(side='right')

    def close(self):
        if self.busy:
            self.closing=True;self.stop.set();self.status.set('Finishing the current photo safely before closing…');return
        self.preview_pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    configure_tools()
    root=tk.Tk();RawFlowApp(root);root.mainloop()


if __name__=='__main__':main()
