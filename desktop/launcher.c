/* A native macOS app entry point embedding the installed open-source Python runtime.
   Keeps the executable inside the app bundle so Cocoa identifies RawFlow's window. */
#import <Cocoa/Cocoa.h>
#include <dlfcn.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int read_resource(const char *contents, const char *name, char *value, size_t size) {
    char path[PATH_MAX];
    snprintf(path, sizeof(path), "%s/Resources/%s", contents, name);
    FILE *file = fopen(path, "r");
    if (!file) return 0;
    int ok = fgets(value, (int)size, file) != NULL;
    fclose(file);
    if (ok) value[strcspn(value, "\r\n")] = '\0';
    return ok && value[0] == '/';
}

int main(int argc, char **argv) {
    (void)argc;
    const char *runtime = getenv("RAWFLOW_PYTHONHOME");
    char executable[PATH_MAX], resolved[PATH_MAX], library[PATH_MAX], contents[PATH_MAX];
    char configured_project[PATH_MAX], configured_runtime[PATH_MAX];
    uint32_t size = sizeof(executable);
    if (_NSGetExecutablePath(executable, &size) || !realpath(executable, resolved)) return 1;
    strcpy(contents, resolved);
    for (int i = 0; i < 2; ++i) *strrchr(contents, '/') = '\0';
    if (read_resource(contents, "python-home.txt", configured_runtime, sizeof(configured_runtime))) runtime = configured_runtime;
    if (!runtime) { fprintf(stderr, "Configure python-home.txt or RAWFLOW_PYTHONHOME before launching.\n"); return 1; }
    // .../Photo-Editor/RawFlow.app/Contents/MacOS/RawFlow -> project root
    for (int i = 0; i < 4; ++i) {
        char *slash = strrchr(resolved, '/');
        if (!slash) return 1;
        *slash = '\0';
    }
    if (read_resource(contents, "project-path.txt", configured_project, sizeof(configured_project))) strcpy(resolved, configured_project);
    setenv("PYTHONHOME", runtime, 1);
    setenv("PYTHONPATH", resolved, 1);
    snprintf(library, sizeof(library), "%s/lib/libpython3.12.dylib", runtime);
    void *handle = dlopen(library, RTLD_NOW | RTLD_GLOBAL);
    if (!handle) { fprintf(stderr, "RawFlow cannot load Python: %s\n", dlerror()); return 1; }
    int (*python_main)(int, char **) = (int (*)(int, char **))dlsym(handle, "Py_BytesMain");
    if (!python_main) return 1;
    char *python_args[] = {argv[0], "-m", "rawflow.gui", NULL};
    return python_main(3, python_args);
}

/* Tk has initialized its NSApplication by the time Python calls this. */
void RawFlowSetApplicationIcon(const char *path) {
    @autoreleasepool {
        NSImage *icon = [[NSImage alloc] initWithContentsOfFile:[NSString stringWithUTF8String:path]];
        if (icon) {
            [NSApp setApplicationIconImage:icon];
            [icon release];
        }
    }
}
