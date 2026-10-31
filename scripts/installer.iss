; Inno Setup Installer Script for A1 Mini Pen Plotter
[Setup]
AppId={{8D6B9E10-3C74-4F18-9B14-A10180180001}
AppName=A1 Mini Pen Plotter
AppVersion=1.10.2
AppPublisher=A1 Mini Pen Plotter Engineering
DefaultDirName={autopf}\A1 Mini Pen Plotter
DefaultGroupName=A1 Mini Pen Plotter
OutputDir=..\dist
OutputBaseFilename=A1_Mini_Pen_Plotter_Setup_v1.10.2
SetupIconFile=..\app\resources\icon.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Files]
Source: "..\dist\A1 Mini Pen Plotter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\A1 Mini Pen Plotter"; Filename: "{app}\A1 Mini Pen Plotter.exe"
Name: "{autodesktop}\A1 Mini Pen Plotter"; Filename: "{app}\A1 Mini Pen Plotter.exe"
