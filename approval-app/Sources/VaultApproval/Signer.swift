import Foundation
import CryptoKit
import LocalAuthentication
import Security

struct EnclaveSigner {
    let folder: URL
    init() {
        folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("VaultApproval", isDirectory: true)
    }
    var keyURL: URL { folder.appendingPathComponent("approval-key.enclave") }

    func context(_ reason: String) -> LAContext {
        let context = LAContext()
        context.localizedReason = reason
        context.touchIDAuthenticationAllowableReuseDuration = 0
        return context
    }

    func enroll(export: URL) throws {
        guard SecureEnclave.isAvailable else {
            throw ApprovalError(message: "Secure Enclave is unavailable. No software-key fallback is permitted.")
        }
        let auth = context("Set up vault batch approvals")
        defer { auth.invalidate() }
        let key: SecureEnclave.P256.Signing.PrivateKey
        if FileManager.default.fileExists(atPath: keyURL.path) {
            key = try .init(dataRepresentation: Data(contentsOf: keyURL), authenticationContext: auth)
        } else {
            var error: Unmanaged<CFError>?
            guard let access = SecAccessControlCreateWithFlags(
                nil, kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
                [.privateKeyUsage, .userPresence], &error
            ) else {
                throw ApprovalError(message: "Could not configure protected key access.")
            }
            key = try .init(accessControl: access, authenticationContext: auth)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
                                                     attributes: [.posixPermissions: 0o700])
            try key.dataRepresentation.write(to: keyURL, options: .withoutOverwriting)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: keyURL.path)
        }
        let payload = ["approval_scheme": "p256-sha256",
                       "approval_public_key": key.publicKey.x963Representation.base64EncodedString()]
        try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
            .write(to: export, options: .withoutOverwriting)
    }

    func sign(_ request: ReviewRequest) throws -> Data {
        guard SecureEnclave.isAvailable else {
            throw ApprovalError(message: "Secure Enclave unavailable. Approval was not issued.")
        }
        let auth = context("Approve vault proposal \(request.proposalID.prefix(12)) — \(request.actions.count) files")
        defer { auth.invalidate() }
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            dataRepresentation: Data(contentsOf: keyURL), authenticationContext: auth)
        guard key.publicKey.x963Representation == request.publicKey else {
            throw ApprovalError(message: "The enrolled key differs from this proposal's configured approval key.")
        }
        // Authentication is enforced by the key operation, not by a separate UI boolean.
        let signature = try key.signature(for: request.messageData)
        let message = try JSONSerialization.jsonObject(with: request.messageData)
        return try JSONSerialization.data(withJSONObject: ["message": message,
                "signature": signature.derRepresentation.base64EncodedString()],
                options: [.sortedKeys])
    }
}
