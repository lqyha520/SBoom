Option Explicit

Dim shell, command, exitCode, files, localCa
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
localCa = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\learn-coach\local-backend-ca.pem")
If files.FileExists(localCa) Then
  shell.Environment("PROCESS")("NODE_EXTRA_CA_CERTS") = localCa
End If
shell.CurrentDirectory = WScript.Arguments(2)
command = Chr(34) & WScript.Arguments(0) & Chr(34) & " " & Chr(34) & WScript.Arguments(1) & Chr(34)
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
