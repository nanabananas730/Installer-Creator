import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess
import os
import threading
import tempfile

CONFIG_FILE = "installer_config.txt"

def load_config():
    config = {"mingw": r"C:\mingw64\bin", "7zip": ""}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    config[key] = val
    return config

def save_config(*args):
    with open(CONFIG_FILE, "w") as f:
        f.write(f"mingw={mingw_path_var.get().strip()}\n")
        f.write(f"7zip={sevenzip_path_var.get().strip()}\n")

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow: return
        x, y, _, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="lightyellow",
                         relief="solid", borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack()

    def hide(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

C_TEMPLATE = """
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
#include <shellapi.h>

#define IDR_7ZR 101
#define IDR_ARCHIVE 102
#define IDR_UNINST 103

typedef struct {{
    const char* target;
    const char* name;
    int isStartMenu;
    const char* customIcon;
}} ShortcutDef;

const char* PROG_NAME = "{prog_name}";
const char* MODE_TYPE = "{mode_type}";
const char* SUB_DIR = "{sub_dir}";
int DO_REGISTER = {do_register};
const char* PROG_PUB = "{prog_pub}";
const char* PROG_VER = "{prog_ver}";
const char* REG_ICON = "{reg_icon}";

ShortcutDef SHORTCUTS[] = {{
{shortcuts_array}
}};
int SHORTCUT_COUNT = {shortcut_count};

BOOL IsUserAdmin() {{
    BOOL b = FALSE;
    SID_IDENTIFIER_AUTHORITY NtAuthority = SECURITY_NT_AUTHORITY;
    PSID AdministratorsGroup;
    if (AllocateAndInitializeSid(&NtAuthority, 2, SECURITY_BUILTIN_DOMAIN_RID, DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &AdministratorsGroup)) {{
        CheckTokenMembership(NULL, AdministratorsGroup, &b);
        FreeSid(AdministratorsGroup);
    }}
    return b;
}}

void ElevateSelf(const char* args) {{
    char szPath[MAX_PATH];
    GetModuleFileName(NULL, szPath, MAX_PATH);
    ShellExecute(NULL, "runas", szPath, args, NULL, SW_SHOWNORMAL);
    ExitProcess(0);
}}

void ExtractResource(int id, const char* outPath) {{
    HRSRC hRes = FindResource(NULL, MAKEINTRESOURCE(id), RT_RCDATA);
    if (!hRes) return;
    HGLOBAL hMem = LoadResource(NULL, hRes);
    DWORD size = SizeofResource(NULL, hRes);
    void* pData = LockResource(hMem);
    
    FILE* f = fopen(outPath, "wb");
    if (f) {{
        fwrite(pData, 1, size, f);
        fclose(f);
    }}
}}

void CreateShortcut(const char* exePath, const char* linkPath, const char* iconPath) {{
    CoInitialize(NULL);
    IShellLink* psl;
    if (SUCCEEDED(CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLink, (LPVOID*)&psl))) {{
        psl->lpVtbl->SetPath(psl, exePath);
        
        if (iconPath && strlen(iconPath) > 0) {{
            psl->lpVtbl->SetIconLocation(psl, iconPath, 0); 
        }}

        IPersistFile* ppf;
        if (SUCCEEDED(psl->lpVtbl->QueryInterface(psl, &IID_IPersistFile, (LPVOID*)&ppf))) {{
            WCHAR wsz[MAX_PATH];
            MultiByteToWideChar(CP_ACP, 0, linkPath, -1, wsz, MAX_PATH);
            ppf->lpVtbl->Save(ppf, wsz, TRUE);
            ppf->lpVtbl->Release(ppf);
        }}
        psl->lpVtbl->Release(psl);
    }}
    CoUninitialize();
}}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {{
    int isAllUsers = 0;

    if (strstr(lpCmdLine, "/ALLUSERS") != NULL) {{
        isAllUsers = 1;
    }} else if (strcmp(MODE_TYPE, "ProgramFiles") == 0) {{
        isAllUsers = 1;
    }} else if (strcmp(MODE_TYPE, "Ask") == 0) {{
        int res = MessageBox(NULL, "Do you want to install this application for All Users?\\n\\n[Yes] For All Users (Requires Admin)\\n[No] For This User Only", PROG_NAME, MB_YESNOCANCEL | MB_ICONQUESTION);
        if (res == IDCANCEL) return 0;
        if (res == IDYES) isAllUsers = 1;
    }}

    if (isAllUsers && !IsUserAdmin()) {{
        ElevateSelf("/ALLUSERS");
        return 0;
    }}

    char targetDir[MAX_PATH];
    if (isAllUsers) {{
        ExpandEnvironmentStrings("%PROGRAMFILES%", targetDir, MAX_PATH);
    }} else {{
        ExpandEnvironmentStrings("%LOCALAPPDATA%", targetDir, MAX_PATH);
    }}
    
    strcat(targetDir, "\\\\");
    strcat(targetDir, SUB_DIR);
    CreateDirectory(targetDir, NULL);

    char tempDir[MAX_PATH], sz7z[MAX_PATH], szArchive[MAX_PATH];
    GetTempPath(MAX_PATH, tempDir);
    sprintf(sz7z, "%s7zr.exe", tempDir);
    sprintf(szArchive, "%sarchive.7z", tempDir);

    ExtractResource(IDR_7ZR, sz7z);
    ExtractResource(IDR_ARCHIVE, szArchive);

    char szUninst[MAX_PATH];
    sprintf(szUninst, "%s\\\\uninstall.exe", targetDir);
    ExtractResource(IDR_UNINST, szUninst);

    char cmd[1024];
    sprintf(cmd, "\\"%s\\" x \\"%s\\" -o\\"%s\\" -y", sz7z, szArchive, targetDir);
    
    STARTUPINFO si = {{ sizeof(si) }};
    PROCESS_INFORMATION pi;
    if (CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {{
        WaitForSingleObject(pi.hProcess, INFINITE);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }}

    for (int i = 0; i < SHORTCUT_COUNT; i++) {{
        char folderPath[MAX_PATH];
        int csidl = 0;
        
        if (SHORTCUTS[i].isStartMenu) {{
            csidl = isAllUsers ? CSIDL_COMMON_PROGRAMS : CSIDL_PROGRAMS;
        }} else {{
            csidl = isAllUsers ? CSIDL_COMMON_DESKTOPDIRECTORY : CSIDL_DESKTOPDIRECTORY;
        }}
        
        if (SUCCEEDED(SHGetFolderPath(NULL, csidl, NULL, 0, folderPath))) {{
            char linkPath[MAX_PATH];
            sprintf(linkPath, "%s\\\\%s.lnk", folderPath, SHORTCUTS[i].name);
            
            char fullExePath[MAX_PATH];
            sprintf(fullExePath, "%s\\\\%s", targetDir, SHORTCUTS[i].target);
            
            char fullIconPath[MAX_PATH] = "";
            if (strlen(SHORTCUTS[i].customIcon) > 0) {{
                sprintf(fullIconPath, "%s\\\\%s", targetDir, SHORTCUTS[i].customIcon);
            }}
            
            CreateShortcut(fullExePath, linkPath, fullIconPath);
        }}
    }}

    if (DO_REGISTER) {{
        HKEY hKey;
        char regPath[512];
        sprintf(regPath, "Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Uninstall\\\\%s", PROG_NAME);
        
        HKEY rootKey = isAllUsers ? HKEY_LOCAL_MACHINE : HKEY_CURRENT_USER;
        
        if (RegCreateKeyEx(rootKey, regPath, 0, NULL, REG_OPTION_NON_VOLATILE, KEY_WRITE | KEY_WOW64_64KEY, NULL, &hKey, NULL) == ERROR_SUCCESS) {{
            char actualUninstall[MAX_PATH];
            sprintf(actualUninstall, "\\"%s\\\\uninstall.exe\\"", targetDir);

            RegSetValueEx(hKey, "DisplayName", 0, REG_SZ, (const BYTE*)PROG_NAME, strlen(PROG_NAME) + 1);
            RegSetValueEx(hKey, "Publisher", 0, REG_SZ, (const BYTE*)PROG_PUB, strlen(PROG_PUB) + 1);
            RegSetValueEx(hKey, "DisplayVersion", 0, REG_SZ, (const BYTE*)PROG_VER, strlen(PROG_VER) + 1);
            RegSetValueEx(hKey, "UninstallString", 0, REG_SZ, (const BYTE*)actualUninstall, strlen(actualUninstall) + 1);
            RegSetValueEx(hKey, "InstallLocation", 0, REG_SZ, (const BYTE*)targetDir, strlen(targetDir) + 1);
            
            if (strlen(REG_ICON) > 0) {{
                char fullRegIcon[MAX_PATH];
                sprintf(fullRegIcon, "%s\\\\%s", targetDir, REG_ICON);
                RegSetValueEx(hKey, "DisplayIcon", 0, REG_SZ, (const BYTE*)fullRegIcon, strlen(fullRegIcon) + 1);
            }}
            
            RegCloseKey(hKey);
        }}
    }}

    DeleteFile(sz7z);
    DeleteFile(szArchive);

    MessageBox(NULL, "Installation complete!", "Success", MB_OK | MB_ICONINFORMATION);
    return 0;
}}
"""

UNINST_TEMPLATE = """
#include <windows.h>
#include <stdio.h>
#include <shellapi.h>
#include <shlobj.h>

const char* PROG_NAME = "{prog_name}";

void RemoveShortcut(int csidl, const char* name) {{
    char folderPath[MAX_PATH], linkPath[MAX_PATH];
    if (SUCCEEDED(SHGetFolderPath(NULL, csidl, NULL, 0, folderPath))) {{
        sprintf(linkPath, "%s\\\\%s.lnk", folderPath, name);
        DeleteFile(linkPath);
    }}
}}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {{
    char msg[256];
    sprintf(msg, "Are you sure you want to uninstall %s?", PROG_NAME);
    if (MessageBox(NULL, msg, "Uninstall", MB_YESNO | MB_ICONQUESTION) != IDYES) return 0;

    char exePath[MAX_PATH], dirPath[MAX_PATH];
    GetModuleFileName(NULL, exePath, MAX_PATH);
    strcpy(dirPath, exePath);
    char *lastSlash = strrchr(dirPath, '\\\\');
    if (lastSlash) *lastSlash = '\\0';

    char localApp[MAX_PATH], progFiles[MAX_PATH];
    ExpandEnvironmentStrings("%LOCALAPPDATA%", localApp, MAX_PATH);
    ExpandEnvironmentStrings("%PROGRAMFILES%", progFiles, MAX_PATH);

    if (lstrcmpiA(dirPath, localApp) == 0 || lstrcmpiA(dirPath, progFiles) == 0 || strlen(dirPath) <= 3) {{
        MessageBox(NULL, "Safety Abort: Cannot delete protected root directory.", "Error", MB_OK | MB_ICONERROR);
        return 1;
    }}

    RemoveShortcut(CSIDL_DESKTOPDIRECTORY, PROG_NAME);
    RemoveShortcut(CSIDL_PROGRAMS, PROG_NAME);
    RemoveShortcut(CSIDL_COMMON_DESKTOPDIRECTORY, PROG_NAME);
    RemoveShortcut(CSIDL_COMMON_PROGRAMS, PROG_NAME);

    char regPath[512];
    sprintf(regPath, "Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Uninstall\\\\%s", PROG_NAME);
    RegDeleteKeyA(HKEY_CURRENT_USER, regPath);
    RegDeleteKeyA(HKEY_LOCAL_MACHINE, regPath);

    char cmd[1024];
    sprintf(cmd, "/c timeout /t 1 /nobreak > nul & del \\"%s\\" & rd /s /q \\"%s\\"", exePath, dirPath);

    SHELLEXECUTEINFO sei = {{0}};
    sei.cbSize = sizeof(sei);
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.lpVerb = "runas"; 
    sei.lpFile = "cmd.exe";
    sei.lpParameters = cmd;
    sei.nShow = SW_HIDE;
    ShellExecuteEx(&sei);

    return 0;
}}
"""

shortcut_rows = []

def add_shortcut_row(target="", name="", location="Desktop", icon_type="Default", icon_path=""):
    row_frame = tk.Frame(shortcuts_frame)
    row_frame.pack(fill="x", pady=2)
    
    t_var = tk.StringVar(value=target)
    n_var = tk.StringVar(value=name)
    l_var = tk.StringVar(value=location)
    i_type_var = tk.StringVar(value=icon_type)
    i_path_var = tk.StringVar(value=icon_path)
    
    tk.Label(row_frame, text="Target:").pack(side="left")
    tk.Entry(row_frame, width=12, textvariable=t_var).pack(side="left", padx=2)
    
    tk.Label(row_frame, text="Name:").pack(side="left")
    tk.Entry(row_frame, width=12, textvariable=n_var).pack(side="left", padx=2)
    
    tk.OptionMenu(row_frame, l_var, "Desktop", "Start Menu").pack(side="left", padx=2)
    
    def toggle_sc_icon(*args):
        if i_type_var.get() == "Custom":
            sc_icon_entry.config(state="normal")
        else:
            sc_icon_entry.config(state="disabled")

    tk.Label(row_frame, text="Icon:").pack(side="left", padx=(5,0))
    i_menu = tk.OptionMenu(row_frame, i_type_var, "Default", "Custom", command=toggle_sc_icon)
    i_menu.pack(side="left")
    
    sc_icon_entry = tk.Entry(row_frame, width=10, textvariable=i_path_var, state="disabled")
    sc_icon_entry.pack(side="left", padx=2)
    ToolTip(sc_icon_entry, "Relative path in 7z, e.g., 'game.exe' or 'assets\\icon.ico'")
    
    toggle_sc_icon()

    btn_del = tk.Button(row_frame, text="X", fg="red", command=lambda: remove_shortcut_row(row_frame))
    btn_del.pack(side="left", padx=5)
    
    shortcut_rows.append({
        "frame": row_frame, 
        "target": t_var, 
        "name": n_var, 
        "loc": l_var, 
        "i_type": i_type_var, 
        "i_path": i_path_var
    })

def remove_shortcut_row(frame):
    global shortcut_rows
    shortcut_rows = [r for r in shortcut_rows if r["frame"] != frame]
    frame.destroy()

def run_compile(mingw_bin, seven_zip, archive, out_exe, config):
    temp_dir = tempfile.mkdtemp()
    c_file = os.path.join(temp_dir, "installer.c")
    uninst_c_file = os.path.join(temp_dir, "uninstaller.c")
    uninst_exe = os.path.join(temp_dir, "uninstall.exe")
    rc_file = os.path.join(temp_dir, "resources.rc")
    res_file = os.path.join(temp_dir, "resources.res")

    try:
        gcc_path = os.path.join(mingw_bin, "gcc.exe")
        
        uninst_code = UNINST_TEMPLATE.format(prog_name=config["prog_name"])
        with open(uninst_c_file, "w") as f:
            f.write(uninst_code)
            
        uninst_cmd = [
            gcc_path, uninst_c_file, "-o", uninst_exe,
            "-Os", "-s", "-mwindows", "-ladvapi32", "-lshell32"
        ]
        subprocess.run(uninst_cmd, check=True)

        c_code = C_TEMPLATE.format(**config)
        with open(c_file, "w") as f:
            f.write(c_code)

        escaped_7z = seven_zip.replace("\\", "\\\\")
        escaped_archive = archive.replace("\\", "\\\\")
        escaped_uninst = uninst_exe.replace("\\", "\\\\")
        
        rc_content = f'101 RCDATA "{escaped_7z}"\n102 RCDATA "{escaped_archive}"\n103 RCDATA "{escaped_uninst}"\n'
        
        if config["icon_path"]:
            escaped_icon = config["icon_path"].replace("\\", "\\\\")
            rc_content += f'IDI_ICON1 ICON "{escaped_icon}"\n'
            
        with open(rc_file, "w") as f:
            f.write(rc_content)

        windres_path = os.path.join(mingw_bin, "windres.exe")
        subprocess.run([windres_path, rc_file, "-O", "coff", "-o", res_file], check=True)

        cmd = [
            gcc_path, c_file, res_file, "-o", out_exe,
            "-Os", "-s", "-mwindows",
            "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
            "-lole32", "-luuid", "-lshell32", "-ladvapi32"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            messagebox.showerror("GCC Error", result.stderr or "Unknown error")
            return

        messagebox.showinfo("Success", f"Installer Generated:\n{out_exe}")
        
    except Exception as e:
        messagebox.showerror("Error", f"Failed:\n{e}")
    finally:
        compile_button.config(state="normal")
        status_label.config(text="")

def start_compile():
    mingw_bin = mingw_path_var.get().strip()
    seven_zip = sevenzip_path_var.get().strip()
    archive = archive_var.get().strip()
    prog_name = name_var.get().strip()
    
    if not os.path.isdir(mingw_bin) or not os.path.isfile(seven_zip) or not os.path.isfile(archive):
        messagebox.showerror("Error", "Check paths. Missing MinGW, 7-Zip, or Archive.")
        return
    if not prog_name:
        messagebox.showerror("Error", "Program Name is required.")
        return

    sub_dir = path_suffix_var.get().strip()
    if not sub_dir or sub_dir in ["\\", "/"]:
        messagebox.showerror("Error", "Installation Path Suffix cannot be empty!\nYou must specify a folder to prevent the uninstaller from wiping root directories.")
        return

    out_exe = filedialog.asksaveasfilename(defaultextension=".exe", filetypes=[("Executable", "*.exe")], initialfile=f"{prog_name}_Installer.exe")
    if not out_exe: return

    compile_button.config(state="disabled")
    status_label.config(text="Generating Installer...")

    sc_items = []
    for row in shortcut_rows:
        t = row["target"].get().strip().replace("\\", "\\\\")
        n = row["name"].get().strip()
        is_sm = 1 if row["loc"].get() == "Start Menu" else 0
        i_val = row["i_path"].get().strip().replace("\\", "\\\\") if row["i_type"].get() == "Custom" else ""
        
        if t and n:
            sc_items.append(f'    {{"{t}", "{n}", {is_sm}, "{i_val}"}}')
            
    shortcuts_array = ",\n".join(sc_items)
    
    reg_icon_val = reg_icon_path_var.get().strip().replace("\\", "\\\\") if reg_icon_var.get() == "Custom" else ""

    config = {
        "prog_name": prog_name,
        "mode_type": install_type_var.get(),
        "sub_dir": sub_dir,
        "do_register": reg_var.get(),
        "prog_pub": pub_var.get().strip(),
        "prog_ver": ver_var.get().strip(),
        "reg_icon": reg_icon_val,
        "icon_path": icon_var.get().strip() if include_icon_var.get() else "",
        "shortcuts_array": shortcuts_array,
        "shortcut_count": len(sc_items)
    }

    threading.Thread(target=run_compile, args=(mingw_bin, seven_zip, archive, out_exe, config), daemon=True).start()

def toggle_reg(*args):
    state = "normal" if reg_var.get() else "disabled"
    pub_entry.config(state=state)
    ver_entry.config(state=state)
    reg_icon_menu.config(state=state)
    if reg_var.get() and reg_icon_var.get() == "Custom":
        reg_icon_entry.config(state="normal")
    else:
        reg_icon_entry.config(state="disabled")

def toggle_icon():
    state = "normal" if include_icon_var.get() else "disabled"
    icon_entry.config(state=state)
    browse_icon_btn.config(state=state)

def update_path_prefix(*args):
    mode = install_type_var.get()
    if mode == "Ask":
        prefix_label.config(text="%default% \\")
    elif mode == "AppData":
        prefix_label.config(text="%LOCALAPPDATA% \\")
    else:
        prefix_label.config(text="%PROGRAMFILES% \\")

root = tk.Tk()
root.title("Installer Creator")
root.geometry("680x850") 
root.resizable(False, False)

cfg = load_config()

mingw_path_var = tk.StringVar(value=cfg["mingw"])
sevenzip_path_var = tk.StringVar(value=cfg["7zip"])
archive_var = tk.StringVar()
install_type_var = tk.StringVar(value="Ask")
path_suffix_var = tk.StringVar()

name_var = tk.StringVar()
reg_var = tk.IntVar(value=0)
pub_var = tk.StringVar()
ver_var = tk.StringVar()
reg_icon_var = tk.StringVar(value="Default")
reg_icon_path_var = tk.StringVar()

include_icon_var = tk.IntVar(value=0)
icon_var = tk.StringVar()

mingw_path_var.trace_add("write", save_config)
sevenzip_path_var.trace_add("write", save_config)
install_type_var.trace_add("write", update_path_prefix)

tk.Label(root, text="MinGW bin Path:").pack(pady=(5, 0))
tk.Entry(root, width=70, textvariable=mingw_path_var).pack()

frame_7z = tk.Frame(root)
tk.Label(frame_7z, text="7-Zip Path (7zr.exe):").pack(side="left")
info_7z = tk.Label(frame_7z, text=" [ i ] ", fg="blue", cursor="question_arrow")
info_7z.pack(side="left")
ToolTip(info_7z, "Recommended version: 7zr.exe\n\nLegal: When distributing your installer, add a note next to the download button for the 7-Zip license.")
frame_7z.pack(pady=(5, 0))
frame_7z_entry = tk.Frame(root)
tk.Entry(frame_7z_entry, width=60, textvariable=sevenzip_path_var).pack(side="left")
tk.Button(frame_7z_entry, text="Browse", command=lambda: sevenzip_path_var.set(filedialog.askopenfilename(filetypes=[("Exe", "*.exe")]))).pack(side="left", padx=5)
frame_7z_entry.pack()

tk.Canvas(root, height=1, bg="gray", width=640).pack(pady=10)

tk.Label(root, text="Program Name:").pack()
tk.Entry(root, width=50, textvariable=name_var).pack()

tk.Checkbutton(root, text="Register Program (Programs & Features)", variable=reg_var, command=toggle_reg).pack(pady=3)
frame_reg = tk.Frame(root)
tk.Label(frame_reg, text="Publisher:").grid(row=0, column=0, sticky="e")
pub_entry = tk.Entry(frame_reg, textvariable=pub_var, state="disabled")
pub_entry.grid(row=0, column=1, padx=5, pady=2)

tk.Label(frame_reg, text="Version:").grid(row=1, column=0, sticky="e")
ver_entry = tk.Entry(frame_reg, textvariable=ver_var, state="disabled")
ver_entry.grid(row=1, column=1, padx=5, pady=2)

tk.Label(frame_reg, text="Uninstall Icon:").grid(row=2, column=0, sticky="e")
frame_reg_icon = tk.Frame(frame_reg)
reg_icon_menu = tk.OptionMenu(frame_reg_icon, reg_icon_var, "Default", "Custom", command=toggle_reg)
reg_icon_menu.config(state="disabled")
reg_icon_menu.pack(side="left")
reg_icon_entry = tk.Entry(frame_reg_icon, width=15, textvariable=reg_icon_path_var, state="disabled")
reg_icon_entry.pack(side="left", padx=5)
ToolTip(reg_icon_entry, "Relative path to .exe or .ico inside the 7z archive")
frame_reg_icon.grid(row=2, column=1, sticky="w", pady=2)

frame_reg.pack()

tk.Canvas(root, height=1, bg="gray", width=640).pack(pady=10)

tk.Label(root, text="Select .7z Archive to Embed:").pack()
tk.Label(root, text="⚠️ WARNING: Archive must contain RAW FILES, NOT a single master folder.", fg="red", font=("Arial", 8, "bold")).pack()
frame_arch = tk.Frame(root)
tk.Entry(frame_arch, width=60, textvariable=archive_var).pack(side="left")
tk.Button(frame_arch, text="Browse", command=lambda: archive_var.set(filedialog.askopenfilename(filetypes=[("7-Zip", "*.7z")]))).pack(side="left", padx=5)
frame_arch.pack()

tk.Label(root, text="Install Location Subdirectory (required):").pack(pady=(5, 0))
frame_path = tk.Frame(root)
tk.OptionMenu(frame_path, install_type_var, "Ask", "AppData", "ProgramFiles").pack(side="left", padx=5)
prefix_label = tk.Label(frame_path, text="%default% \\")
prefix_label.pack(side="left")
tk.Entry(frame_path, width=30, textvariable=path_suffix_var).pack(side="left")
frame_path.pack()

tk.Canvas(root, height=1, bg="gray", width=640).pack(pady=10)

frame_sc_header = tk.Frame(root)
tk.Label(frame_sc_header, text="Shortcuts", font=("Arial", 9, "bold")).pack(side="left")
tk.Button(frame_sc_header, text="+ Add Shortcut", command=add_shortcut_row).pack(side="left", padx=10)
frame_sc_header.pack()

shortcuts_frame = tk.Frame(root)
shortcuts_frame.pack(pady=5)

add_shortcut_row()

tk.Canvas(root, height=1, bg="gray", width=640).pack(pady=10)

tk.Checkbutton(root, text="Include App Icon (For the Installer .exe itself)", variable=include_icon_var, command=toggle_icon).pack()
frame_icon = tk.Frame(root)
icon_entry = tk.Entry(frame_icon, width=50, textvariable=icon_var, state="disabled")
icon_entry.pack(side="left")
browse_icon_btn = tk.Button(frame_icon, text="Browse", state="disabled", command=lambda: icon_var.set(filedialog.askopenfilename(filetypes=[("Icon", "*.ico")])))
browse_icon_btn.pack(side="left", padx=5)
frame_icon.pack()

compile_button = tk.Button(root, text="Generate Installer", font=("Arial", 10, "bold"), command=start_compile)
compile_button.pack(pady=10)
status_label = tk.Label(root, text="", fg="blue")
status_label.pack()

root.mainloop()