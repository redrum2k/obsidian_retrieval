// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "VaultApproval", platforms: [.macOS(.v13)],
    products: [.executable(name: "VaultApproval", targets: ["VaultApproval"])],
    targets: [
        .executableTarget(name: "VaultApproval")
    ]
)
