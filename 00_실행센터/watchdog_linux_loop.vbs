' ===================================================================
' Prism (Linux/WSL) watchdog LOOP - runs watchdog_linux.vbs every 2 min.
'   - Keeps WSL(prism service) and the Cloudflare tunnel alive.
'   - Silent (wscript, no window). Auto-started at logon.
' ===================================================================
Option Explicit
Dim sh, fso, q, single
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
single = fso.GetParentFolderName(WScript.ScriptFullName) & "\watchdog_linux.vbs"
Do
  If fso.FileExists(single) Then
    sh.Run "wscript " & q & single & q, 0, True
  End If
  WScript.Sleep 120000   ' 2 minutes
Loop
