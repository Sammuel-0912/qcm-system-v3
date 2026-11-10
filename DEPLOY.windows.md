# 部署到 Windows 主機（安裝檔，免 Docker、免外網）

把整套系統裝在產線網的**一台** Windows 主機上，電腦和平板都用瀏覽器連這台。規格見 [spec.md §21](spec.md)。

## 交給對方的檔案

**只要一個檔案：`desktop\output\QCM-Setup.exe`（約 50 MB）。**
Python、套件、前端、資料庫都已經包在裡面，目標主機不需要連網，也不需要另外安裝任何東西。

`desktop\` 資料夾裡的其他檔案（`build.ps1`、`installer.iss`、`build\`、`vendor\`⋯）只是用來**產生**安裝檔的，不用給對方。

## 安裝（目標主機）

需求：Windows 10／11 64 位元、系統管理員權限。

1. 把 `QCM-Setup.exe` 複製到主機（USB 隨身碟、網路芳鄰皆可），按兩下執行。
   出現「Windows 已保護您的電腦」時，按 **其他資訊 → 仍要執行**（安裝檔沒有程式碼簽章）。
2. 設定第一位最高權限管理者的帳號與密碼（至少 8 碼），以及網頁埠號（預設 8080）。
3. 安裝完成後，系統以 Windows 服務「QCM」在背景執行，開機自動啟動，不用登入 Windows。
4. 完成頁的「立即開啟網頁」預設已勾選，按「完成」就會用 `http://localhost:8080` 打開登入頁。
   看得到登入頁、用剛設定的帳號登得進去，就表示安裝成功（localhost 不受 Wi-Fi IP 變動影響）。
   之後在這台主機上用桌面捷徑「QCM 品控力平台」開啟。
   平板／其他電腦：瀏覽器開 `http://<這台主機的 IP>:8080`（IP 用命令提示字元執行 `ipconfig` 查詢）。

### 安裝前請 IT 確認

- 主機**固定 IP**，電源設定**不要睡眠**。
- 平板的 Wi-Fi 與主機網段互通（沒有 VLAN 隔離或用戶端隔離）。
- 企業防毒若攔截，請將 `C:\Program Files\QCM` 加入信任清單。

## 更新

在開發機產生新版 `QCM-Setup.exe`，到主機上直接執行即可。帳號、資料與照片都會保留。

## 備份與還原

所有資料都在 `C:\ProgramData\QCM`：

| 檔案 | 內容 |
|---|---|
| `qcm.db` | 資料庫 |
| `ar-uploads\` | 拍照點檢照片 |
| `settings.json` | 埠號、登入金鑰 |
| `logs\` | 服務記錄 |

備份：以系統管理員開命令提示字元，先停服務再複製整個資料夾：

```bat
sc stop QCM
robocopy "C:\ProgramData\QCM" "D:\QCM-backup\%date:~0,4%%date:~5,2%%date:~8,2%" /E
sc start QCM
```

還原：停服務 → 把備份資料夾內容複製回 `C:\ProgramData\QCM` → 啟動服務。

## 打不開網頁時

以系統管理員執行 `sc.exe query QCM`（PowerShell 裡 `sc` 是別的指令，一定要打 `sc.exe`），再看 `C:\ProgramData\QCM\logs\qcm-service.err.log`。

| 記錄裡看到 | 原因 | 處理 |
|---|---|---|
| `無法使用埠號 8080：[WinError 10013]` | 埠號被 Windows 保留（有 Hyper-V／WSL／Docker 的電腦常見）或被其他程式占用 | 重新執行 `QCM-Setup.exe`（資料保留），在埠號頁改成其他埠號，例如 8765 |

安裝程式會在「下一步」時先檢查埠號，並把選定的埠號登記保留，避免重開機後被 Hyper-V／WSL 佔走。

## 日常維運

| 要做的事 | 方法 |
|---|---|
| 看服務狀態／重啟 | `services.msc` 找「QCM 品控力風險智控平台」，或 `sc query QCM`、`sc stop QCM`、`sc start QCM` |
| 看記錄（啟動失敗、匯入錯誤） | `C:\ProgramData\QCM\logs\qcm-service.out.log`、`.err.log` |
| 解除安裝 | 設定 → 應用程式 →「QCM 品控力風險智控平台」。資料夾 `C:\ProgramData\QCM` 會保留，要完全清除請手動刪除 |
| 忘記管理者密碼 | 由另一位最高權限管理者在「使用者管理」重設 |

## 產生安裝檔（開發機）

需要：Node（npm）、Python 3（決定內附的 Python 版本）、Inno Setup 6（`winget install JRSoftware.InnoSetup`），可連網。

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build.ps1
```

會依序：建置前端 → 下載 Python 官方可嵌入版與 WinSW（第一次）→ 安裝後端套件 → Inno Setup 打包，
產生 `desktop\output\QCM-Setup.exe`。`desktop\build\`、`desktop\vendor\`、`desktop\output\` 都不進 git。

## 限制

- 只有 HTTP：拍照點檢可以用；**AR 點檢需要 HTTPS，不支援**。
- 這台主機的資料與 Zeabur、Docker VM 各自獨立，不會同步。
