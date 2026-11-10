; Inno Setup 6：產生 QCM-Setup.exe（spec §21）。由 build.ps1 呼叫，版本號從命令列 /DAppVersion= 帶入。
; 程式裝在 Program Files\QCM；設定與資料在 %ProgramData%\QCM，解除安裝時保留。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1B7A4E-3C1D-4D2A-9E55-0C2B9A7D1E31}
AppName=QCM 品控力風險智控平台
AppVersion={#AppVersion}
AppPublisher=CNE WJ1 DCS
DefaultDirName={autopf}\QCM
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=QCM-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=QCM 品控力風險智控平台

[Languages]
; Inno Setup 沒有內建繁體中文；語系檔取自官方 repo 的非官方翻譯（jrsoftware/issrc，tag is-6_7_1）
Name: "cht"; MessagesFile: "ChineseTraditional.isl"

[Files]
; build.ps1 組好的 build\stage：python\（可嵌入版＋套件）、app\、web\、launcher.py、qcm-service.exe／.xml
Source: "build\stage\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; 更新時先清掉舊版的程式檔，避免殘留已移除的套件或頁面
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\web"

[Icons]
Name: "{autodesktop}\QCM 品控力平台"; Filename: "http://localhost:{code:GetPort}"

[Run]
; 完成頁的勾選（預設勾選）：用 localhost 開網頁，馬上確認安裝成功；以安裝者本人（非系統管理員身分）開瀏覽器
Filename: "http://localhost:{code:GetPort}"; Description: "立即開啟網頁（http://localhost:{code:GetPort}）"; Flags: postinstall shellexec nowait skipifsilent runasoriginaluser; Check: IsServerReady

[UninstallRun]
Filename: "{app}\qcm-service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "{app}\qcm-service.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""QCM"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveFirewall"

[Code]
var
  AdminPage: TInputQueryWizardPage;
  Fresh: Boolean;        { 精靈開始時還沒有 settings.json＝首次安裝 }
  ServerReady: Boolean;  { 服務啟動後 /health 有回應 }

function DataDir: String;
begin
  Result := ExpandConstant('{commonappdata}\QCM');
end;

function SettingsFile: String;
begin
  Result := DataDir + '\settings.json';
end;

{ 從既有的 settings.json 讀 port（更新安裝時用），讀不到就用 8080 }
function ExistingPort: String;
var
  Text: AnsiString;
  S: String;
  I: Integer;
begin
  Result := '8080';
  if not LoadStringFromFile(SettingsFile, Text) then Exit;
  S := String(Text);
  I := Pos('"port":', S);
  if I = 0 then Exit;
  S := Trim(Copy(S, I + 7, 20));
  I := 1;
  Result := '';
  while (I <= Length(S)) and (S[I] >= '0') and (S[I] <= '9') do
  begin
    Result := Result + S[I];
    I := I + 1;
  end;
  if Result = '' then Result := '8080';
end;

function GetPort(Param: String): String;
begin
  Result := Trim(AdminPage.Values[3]);
end;

function IsServerReady: Boolean;
begin
  Result := ServerReady;
end;

function JsonEscape(S: String): String;
begin
  StringChangeEx(S, '\', '\\', True);
  StringChangeEx(S, '"', '\"', True);
  Result := S;
end;

procedure RunHidden(const FileName, Params: String);
var
  Code: Integer;
begin
  Exec(FileName, Params, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

{ localhost:Port 的 /health 是否回 200（服務已就緒，或埠號上跑的就是舊版 QCM） }
function HealthOk(const Port: String): Boolean;
var
  Http: Variant;
begin
  Result := False;
  try
    Http := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Http.SetTimeouts(1000, 1000, 1000, 1000);
    Http.Open('GET', 'http://localhost:' + Port + '/health', False);
    Http.Send('');
    Result := Http.Status = 200;
  except
  end;
end;

{ 把指令輸出存到暫存檔再讀回來 }
function CommandLines(const Params: String; var Lines: TArrayOfString): Boolean;
var
  Tmp: String;
begin
  Tmp := ExpandConstant('{tmp}\qcm-cmd.txt');
  RunHidden(ExpandConstant('{cmd}'), '/c ' + Params + ' > "' + Tmp + '"');
  Result := LoadStringsFromFile(Tmp, Lines);
end;

function FirstToken(var S: String): String;
var
  I: Integer;
begin
  S := Trim(S);
  I := Pos(' ', S);
  if I = 0 then
  begin
    Result := S;
    S := '';
  end
  else
  begin
    Result := Copy(S, 1, I - 1);
    S := Copy(S, I + 1, Length(S));
  end;
end;

{ 埠號不能用的原因；可以用時回傳空字串。
  WinError 10013 多半是 Windows 為 Hyper-V／WSL／Docker 保留了這段埠號，或已有其他程式在用 }
function PortProblem(const PortText: String): String;
var
  Lines: TArrayOfString;
  I, Port, First, Last: Integer;
  S: String;
begin
  Result := '';
  Port := StrToInt(PortText);
  if CommandLines('netsh interface ipv4 show excludedportrange protocol=tcp', Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      S := Lines[I];
      First := StrToIntDef(FirstToken(S), -1);
      Last := StrToIntDef(FirstToken(S), -1);
      if (First > 0) and (Last >= First) and (Port >= First) and (Port <= Last) then
      begin
        Result := 'Windows 已保留 ' + IntToStr(First) + '～' + IntToStr(Last) + ' 這段埠號（Hyper-V／WSL／Docker）';
        Exit;
      end;
    end;
  if HealthOk(PortText) then Exit;  { 正在跑的是舊版 QCM，更新時會先停掉 }
  if CommandLines('netstat -ano -p tcp', Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      if (Pos('LISTENING', Lines[I]) > 0) and (Pos(':' + PortText + ' ', Lines[I]) > 0) then
      begin
        Result := '已有其他程式在使用這個埠號';
        Exit;
      end;
end;

procedure InitializeWizard;
var
  I: Integer;
begin
  Fresh := not FileExists(SettingsFile);
  AdminPage := CreateInputQueryPage(wpWelcome,
    '第一位最高權限管理者', '設定登入帳號與網頁埠號',
    '安裝完成後用這組帳號登入。密碼至少 8 碼，登入後可在右上角選單修改。');
  AdminPage.Add('帳號：', False);
  AdminPage.Add('密碼：', True);
  AdminPage.Add('再輸入一次密碼：', True);
  AdminPage.Add('網頁埠號（平板連線用）：', False);
  AdminPage.Values[0] := 'admin';
  AdminPage.Values[3] := '8080';
  if not Fresh then
  begin
    { 更新安裝：沿用原本的帳號與資料，只能調整埠號 }
    AdminPage.Caption := '網頁埠號';
    AdminPage.Description := '更新安裝會保留原本的帳號與資料';
    AdminPage.SubCaptionLabel.Caption := '原本的埠號無法使用時，可在這裡改成其他埠號（例如 8765）。';
    for I := 0 to 2 do
    begin
      AdminPage.PromptLabels[I].Visible := False;
      AdminPage.Edits[I].Visible := False;
    end;
    AdminPage.Values[3] := ExistingPort;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
  Problem: String;
begin
  Result := True;
  if CurPageID <> AdminPage.ID then Exit;
  Port := StrToIntDef(Trim(AdminPage.Values[3]), 0);
  if Fresh and (Trim(AdminPage.Values[0]) = '') then
  begin
    MsgBox('請輸入帳號。', mbError, MB_OK);
    Result := False;
  end
  else if Fresh and (Length(AdminPage.Values[1]) < 8) then
  begin
    MsgBox('密碼至少 8 碼。', mbError, MB_OK);
    Result := False;
  end
  else if Fresh and (AdminPage.Values[1] <> AdminPage.Values[2]) then
  begin
    MsgBox('兩次輸入的密碼不一致。', mbError, MB_OK);
    Result := False;
  end
  else if (Port < 1) or (Port > 65535) then
  begin
    MsgBox('埠號要是 1～65535 的數字。', mbError, MB_OK);
    Result := False;
  end
  else
  begin
    Problem := PortProblem(IntToStr(Port));
    if Problem <> '' then
    begin
      MsgBox('埠號 ' + IntToStr(Port) + ' 無法使用：' + Problem + '。' + #13#10 +
        '請改用其他埠號，例如 8765。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { 更新安裝：先停掉服務，才能覆蓋執行中的程式檔 }
  if FileExists(ExpandConstant('{app}\qcm-service.exe')) then
    RunHidden(ExpandConstant('{app}\qcm-service.exe'), 'stop');
  Result := '';
end;

procedure WriteSettings;
var
  Lines: TArrayOfString;
begin
  SetArrayLength(Lines, 1);
  Lines[0] := '{"port": ' + GetPort('') +
    ', "adminUsername": "' + JsonEscape(Trim(AdminPage.Values[0])) +
    '", "adminPassword": "' + JsonEscape(AdminPage.Values[1]) + '"}';
  SaveStringsToUTF8File(SettingsFile, Lines, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Service: String;
  I: Integer;
begin
  if CurStep <> ssPostInstall then Exit;
  ForceDirectories(DataDir);
  { 設定檔含 JWT 金鑰與首次管理者密碼：只給 SYSTEM（服務的執行身分）與系統管理員 }
  RunHidden(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F');
  if Fresh then
    WriteSettings
  else if GetPort('') <> ExistingPort then
    { 改埠號：交給 launcher 啟動時寫回 settings.json（不在這裡改寫可能含中文的 JSON） }
    SaveStringToFile(DataDir + '\port-override.txt', GetPort(''), False);

  { 把埠號登記為系統管理員保留：Hyper-V／WSL／Docker 重開機後動態保留埠號時就不會佔走它
   （管理員保留的埠號本程式仍可使用，動態保留的則會 WinError 10013） }
  if (not Fresh) and (GetPort('') <> ExistingPort) then
    RunHidden(ExpandConstant('{sys}\netsh.exe'), 'int ipv4 delete excludedportrange protocol=tcp startport=' +
      ExistingPort + ' numberofports=1 store=persistent');
  RunHidden(ExpandConstant('{sys}\netsh.exe'), 'int ipv4 add excludedportrange protocol=tcp startport=' +
    GetPort('') + ' numberofports=1 store=persistent');

  Service := ExpandConstant('{app}\qcm-service.exe');
  RunHidden(Service, 'install');   { 已註冊過時會失敗，可忽略 }
  RunHidden(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="QCM"');
  RunHidden(ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="QCM" dir=in action=allow protocol=TCP program="' +
    ExpandConstant('{app}\python\python.exe') + '" enable=yes');
  RunHidden(Service, 'start');

  { 等網頁可以連線（最多 60 秒）；連得上才在完成頁提供「立即開啟網頁」 }
  WizardForm.StatusLabel.Caption := '正在啟動 QCM 服務…';
  for I := 1 to 60 do
  begin
    ServerReady := HealthOk(GetPort(''));
    if ServerReady then Break;
    Sleep(1000);
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID <> wpFinished then Exit;
  if ServerReady then
    WizardForm.FinishedLabel.Caption :=
      'QCM 已安裝並在背景執行（Windows 服務「QCM」，開機自動啟動）。' + #13#10#13#10 +
      '這台電腦：http://localhost:' + GetPort('') + #13#10 +
      '平板與其他電腦：http://<這台電腦的 IP>:' + GetPort('') + #13#10 +
      '（IP 可在命令提示字元執行 ipconfig 查詢；建議請 IT 固定這台電腦的 IP）' + #13#10#13#10 +
      '資料與設定在 ' + DataDir + '，請定期備份整個資料夾。'
  else
    WizardForm.FinishedLabel.Caption :=
      '程式已安裝，但 QCM 服務在 60 秒內沒有啟動成功。' + #13#10#13#10 +
      '請以系統管理員開啟下列記錄查看原因：' + #13#10 +
      DataDir + '\logs\qcm-service.err.log' + #13#10#13#10 +
      '若是埠號無法使用，請重新執行這個安裝程式，改用其他埠號（例如 8765）。';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { 解除安裝：釋放安裝時保留的埠號（settings.json 保留不刪，可讀到埠號） }
  if CurUninstallStep = usUninstall then
    RunHidden(ExpandConstant('{sys}\netsh.exe'), 'int ipv4 delete excludedportrange protocol=tcp startport=' +
      ExistingPort + ' numberofports=1 store=persistent');
end;
