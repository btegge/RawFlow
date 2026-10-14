import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from rawflow.gui_jobs import BatchOptions, run_batch, completed_results


class DesktopJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.options=BatchOptions(self.root/'base.pp3',self.root/'evidence.json',self.root/'exports')
        self.events=queue.Queue();self.stop=threading.Event()
        self.paths=[]
        for name in ['one.CR3','two.CR3']:
            p=self.root/name;p.write_bytes(name.encode());self.paths.append(p)
    def tearDown(self):self.tmp.cleanup()
    def messages(self):
        items=[]
        while not self.events.empty():items.append(self.events.get_nowait())
        return items
    def run_job(self, fn, validate=lambda *a:None):
        run_batch(self.paths,self.options,self.events,self.stop,processor=fn,validate=validate)
    def test_progress_and_output_are_delivered(self):
        seen=[]
        def render(raw,base,evidence,out,scene,wb,look,on_progress):
            seen.append((raw,out,look));on_progress('Exporting');out.mkdir()
        self.run_job(render);events=self.messages()
        self.assertEqual([e[0] for e in events].count('completed'),2)
        self.assertEqual(events[-1][1:4],(2,0,False));self.assertTrue(any(e[0]=='progress' for e in events))
        self.assertTrue(all(x[2]=='punchy' for x in seen))
    def test_stopping_finishes_current_photo_and_skips_next(self):
        def render(*args,**kwargs):self.stop.set()
        self.run_job(render)
        events=self.messages();self.assertEqual(events[-1][1:4],(1,0,True))
        self.assertEqual(sum(e[0]=='started' for e in events),1)
    def test_one_bad_photo_does_not_lose_remaining_photos(self):
        def render(raw,*args,**kwargs):
            if raw==self.paths[0]:raise ValueError('broken photo')
        self.run_job(render);events=self.messages()
        self.assertEqual(events[-1][1:3],(1,1));self.assertTrue(any(e[0]=='failed' for e in events))
    def test_failed_compatibility_never_calls_processor(self):
        def validate(*args):raise RuntimeError('stale engine')
        calls=[]
        self.run_job(lambda *args,**kw:calls.append(args),validate)
        events=self.messages();self.assertFalse(calls);self.assertEqual(events[0][0],'fatal')
        self.assertFalse(self.options.output.exists());self.assertEqual(events[-1][1:3],(0,0))
    def test_identical_names_and_content_get_distinct_outputs(self):
        a=self.root/'a';b=self.root/'b';a.mkdir();b.mkdir()
        self.paths=[a/'same.CR3',b/'same.CR3']
        for p in self.paths:p.write_bytes(b'same')
        outputs=[]
        def render(raw,base,evidence,out,*args,**kwargs):outputs.append(out)
        self.run_job(render);self.assertNotEqual(outputs[0],outputs[1])
    def test_original_bytes_are_not_changed(self):
        self.run_job(lambda *args,**kwargs:None)
        self.assertEqual([p.read_bytes() for p in self.paths],[b'one.CR3',b'two.CR3'])
    def test_history_ignores_incomplete_and_malformed_recipes(self):
        for name,data in [('good',{'status':'complete','input':str(self.paths[0])}),('incomplete',{'status':'incomplete'}),('bad',None)]:
            folder=self.root/name;folder.mkdir();(folder/'export.jpg').write_bytes(b'jpeg')
            (folder/'recipe.json').write_text(json.dumps(data) if data else '{')
        self.assertEqual(len(completed_results(self.root)),1)
    def test_history_falls_back_to_preserved_input_copy(self):
        folder=self.root/'result';(folder/'input').mkdir(parents=True)
        (folder/'input/photo.CR3').write_bytes(b'raw');(folder/'export.jpg').write_bytes(b'jpeg')
        (folder/'recipe.json').write_text(json.dumps({'status':'complete','input':'/missing/photo.CR3'}))
        results=completed_results(folder);self.assertEqual(results[0][0],(folder/'input/photo.CR3').resolve())
