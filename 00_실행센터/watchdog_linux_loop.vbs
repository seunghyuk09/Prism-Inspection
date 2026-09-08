' ===================================================================
' Prism (Linux/WSL) watchdog LOOP - runs watchdog_linux.vbs every 2 min.
'   - Keeps WSL(prism service) and the Cloudflare tunnel alive.
'   - Silent (wscript, no window). Auto-started at logon.
' ===================================================================
Option Explicit
Dim sh, fso, q, oneShot
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
oneShot = fso.GetParentFolderName(WScript.ScriptFullName) & "\watchdog_linux.vbs"
Do
  If fso.FileExists(oneShot) Then
    sh.Run "wscript " & q & oneShot & q, 0, True
  End If
  WScript.Sleep 120000   ' 2 minutes
Loop
