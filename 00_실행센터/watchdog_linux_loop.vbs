' ===================================================================
' Prism (Linux/WSL) watchdog LOOP - runs watchdog_linux.vbs every 2 min.
'   - Keeps WSL(prism service) and the Cloudflare tunnel alive.
'   - Silent (wscript, no window). Auto-started at logon.
'
'   Hardened: a transient error (WMI hiccup, file lock, WSL busy) must NOT
'   kill the loop. Windows Task Scheduler is blocked by policy on this PC,
'   so nothing would restart this loop until the next logon.
'   Also writes a heartbeat file so we can tell later whether it was alive.
' ===================================================================
Option Explicit
Dim sh, fso, q, oneShot, beat, fh

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
oneShot = fso.GetParentFolderName(WScript.ScriptFullName) & "\watchdog_linux.vbs"
beat = sh.ExpandEnvironmentStrings("%TEMP%\prism_watchdog_beat.txt")

Do
  On Error Resume Next

  ' heartbeat: this file's mtime = when the watchdog last ran
  Set fh = fso.CreateTextFile(beat, True)
  If Err.Number = 0 Then
    fh.WriteLine Now & " alive"
    fh.Close
  End If
  Err.Clear

  If fso.FileExists(oneShot) Then
    sh.Run "wscript " & q & oneShot & q, 0, True
  End If
  Err.Clear

  On Error GoTo 0
  WScript.Sleep 120000   ' 2 minutes
Loop
