import Foundation
import CryptoKit

struct ApprovalError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

struct ReviewRequest {
    let original: Data
    let body: [String: Any]
    let proposalID: String
    let digest: String
    let publicKey: Data
    let vault: String
    let actions: [[String: Any]]

    init(data: Data) throws {
        guard data.count <= 64 * 1024 * 1024,
              let request = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              request["version"] as? Int == 1,
              request["approval_scheme"] as? String == "p256-sha256",
              let encodedKey = request["approval_public_key"] as? String,
              let key = Data(base64Encoded: encodedKey),
              let canonical = request["canonical_body"] as? String,
              let body = try JSONSerialization.jsonObject(with: Data(canonical.utf8)) as? [String: Any],
              let id = body["id"] as? String,
              let config = body["config"] as? String,
              let context = body["review_context"] as? [String: String],
              let vault = context["vault"], vault.hasPrefix("/"),
              let actions = body["actions"] as? [[String: Any]], !actions.isEmpty,
              actions.count <= 21,
              let sources = body["sources"] as? [[String: Any]], !sources.isEmpty,
              sources.count <= 20,
              Self.isHash(id), Self.isHash(config) else {
            throw ApprovalError(message: "Invalid review request. Export it again with vault approval-request.")
        }
        _ = try P256.Signing.PublicKey(x963Representation: key)
        var seen = Set<String>()
        for action in actions {
            guard let path = action["path"] as? String,
                  !path.hasPrefix("/"), !path.split(separator: "/").contains(".."),
                  !path.isEmpty, !path.contains("\0"), seen.insert(path).inserted,
                  let content = action["content"] as? String,
                  let outputHash = action["output_hash"] as? String,
                  sha256(Data(content.utf8)) == outputHash else {
                throw ApprovalError(message: "Invalid action or content hash. Nothing was approved.")
            }
            if let before = action["before"] as? String {
                guard let expected = action["expected_hash"] as? String,
                      sha256(Data(before.utf8)) == expected else {
                    throw ApprovalError(message: "Baseline hash does not match the displayed text.")
                }
            } else if !(action["before"] is NSNull && action["expected_hash"] is NSNull) {
                throw ApprovalError(message: "A create action must explicitly specify an absent baseline.")
            }
        }
        original = data
        self.body = body
        proposalID = id
        digest = sha256(Data(canonical.utf8))
        publicKey = key
        self.vault = vault
        self.actions = actions
    }

    static func isHash(_ value: String) -> Bool {
        value.count == 64 && value.allSatisfy { "0123456789abcdef".contains($0) }
    }

    // All values are validated ASCII hex; matches Python canonical() exactly.
    var messageData: Data {
        Data("{\"decision\":\"approve\",\"proposal_digest\":\"\(digest)\",\"proposal_id\":\"\(proposalID)\"}".utf8)
    }

    var reviewText: String {
        var text = "Vault: \(vault)\nProposal: \(proposalID)\nDigest: \(digest)\nConfiguration: \(body["config"]!)\n\n"
        text += "Review every file below. Original and replacement text are complete, not excerpts.\n"
        for action in actions {
            text += "\n========== \(action["path"]!) ==========\n"
            text += "EXPECTED HASH: \(action["expected_hash"]!)\nOUTPUT HASH: \(action["output_hash"]!)\n"
            text += "\n--- BEFORE (complete) ---\n\(action["before"] as? String ?? "[New file: no previous content]")\n"
            text += "\n+++ AFTER (complete) +++\n\(action["content"]!)\n"
        }
        var metadata = body
        metadata.removeValue(forKey: "actions")
        if let bytes = try? JSONSerialization.data(withJSONObject: metadata, options: [.prettyPrinted, .sortedKeys]),
           let json = String(data: bytes, encoding: .utf8) {
            text += "\n========== SOURCES, GROUNDING AND ALL PROPOSAL METADATA ==========\n\(json)\n"
        }
        return text
    }
}
