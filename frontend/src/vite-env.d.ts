/// <reference types="vite/client" />

// A-Frame 以 classic script 注入後才會註冊這些自訂元素，
// React 的 JSX 型別不認得它們——但本專案是用 document.createElement 動態建立，
// 不經 JSX，因此只需要宣告 ?url 匯入即可（vite/client 已涵蓋）。
