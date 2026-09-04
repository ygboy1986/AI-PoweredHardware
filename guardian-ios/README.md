# iOS 调用 Guardian AI

将 `GuardianAPIClient.swift` 拖入 iOS App target；将 `GuardianAPIClientTests.swift` 拖入 Unit Test target，并将测试文件中的 `@testable import GuardianIOS` 改成实际 App 模块名。

## 真机与模拟器地址

- iOS 模拟器：`http://127.0.0.1:8000/`。
- 真实 iPhone：Mac 上的 API 必须监听 `0.0.0.0`，App 使用 Mac 局域网 IP，例如 `http://192.168.1.10:8000/`；手机和 Mac 必须在同一网络。

开发期 HTTP 请求还需要在 App 的 `Info.plist` 临时加入 ATS 例外。生产环境必须使用 HTTPS，且不应保留此例外。
