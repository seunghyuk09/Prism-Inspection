' ===================================================================
' Prism web server watchdog (ASCII only) - keep port 10000 alive.
'  - Paths resolved at runtime from this script's location + env vars,
'    so no non-ASCII literals are stored in this file.
'  - Run silently via wscript (no console window). Safe to run often.
' ===================================================================
Option Explicit
Dim sh, fso, q, root, py, rs, chk, up
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)

' project root = parent of this script's folder (00_실행센터)
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
py = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
rs = root & "\run_server.py"
chk = sh.ExpandEnvironmentStrings("%TEMP%\prism_web_chk.txt")

' is port 10000 listening?
sh.Run "cmd /c netstat -ano | findstr LISTENING | findstr " & q & ":10000" & q & " > " & q & chk & q, 0, True

up = False
If fso.FileExists(chk) Then
  If fso.GetFile(chk).Size > 0 Then up = True
End If

' if down, relaunch the server hidden (pythonw = no window)
If Not up Then
  If fso.FileExists(py) And fso.FileExists(rs) Then
    sh.Run q & py & q & " " & q & rs & q & " 10000", 0, False
  End If
End If
