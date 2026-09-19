import Foundation
import CryptoKit

func check(_ condition: Bool, _ message: String) {
    if !condition { fatalError(message) }
}
func fixture() throws -> Data {
    let content = "# Note\nα and 🧬\n"
    let body: [String: Any] = [
        "id": String(repeating: "a", count: 64), "config": String(repeating: "b", count: 64),
        "review_context": ["vault": "/isolated/sample-vault"],
        "sources": [["path": "Study/Raw/Capture.md", "grounding": "Isolated test fixture"]],
        "actions": [["path": "Study/Notes/Note.md", "before": NSNull(),
                     "expected_hash": NSNull(), "content": content,
                     "output_hash": sha256(Data(content.utf8))]]]
    let raw = String(data: try JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]), encoding: .utf8)!
    let key = P256.Signing.PrivateKey().publicKey.x963Representation.base64EncodedString()
    return try JSONSerialization.data(withJSONObject: ["version": 1, "canonical_body": raw,
         "approval_scheme": "p256-sha256", "approval_public_key": key])
}
let valid = try fixture()
let request = try ReviewRequest(data: valid)
check(request.reviewText.contains("α and 🧬"), "Unicode text omitted")
check(request.reviewText.contains("Study/Notes/Note.md"), "Path omitted")
check(String(data: request.messageData, encoding: .utf8) ==
      "{\"decision\":\"approve\",\"proposal_digest\":\"\(request.digest)\",\"proposal_id\":\"\(request.proposalID)\"}", "Canonical message mismatch")
var outer = try JSONSerialization.jsonObject(with: valid) as! [String: Any]
var body = try JSONSerialization.jsonObject(with: Data((outer["canonical_body"] as! String).utf8)) as! [String: Any]
var actions = body["actions"] as! [[String: Any]]
actions[0]["content"] = "tampered"
body["actions"] = actions
outer["canonical_body"] = String(data: try JSONSerialization.data(withJSONObject: body), encoding: .utf8)!
for invalid in [Data("{}".utf8), try JSONSerialization.data(withJSONObject: outer)] {
    do { _ = try ReviewRequest(data: invalid); fatalError("Invalid request accepted") }
    catch { }
}
if CommandLine.arguments.count == 2 {
    let dir = URL(fileURLWithPath: CommandLine.arguments[1])
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    try valid.write(to: dir.appendingPathComponent("request.json"))
    // Software key is an interoperability fixture only, never a production fallback.
    let testKey = P256.Signing.PrivateKey()
    let output: [String: Any] = ["public_key": testKey.publicKey.x963Representation.base64EncodedString(),
      "message": try JSONSerialization.jsonObject(with: request.messageData),
      "signature": try testKey.signature(for: request.messageData).derRepresentation.base64EncodedString()]
    try JSONSerialization.data(withJSONObject: output).write(to: dir.appendingPathComponent("swift-signature.json"))
}
print("Review parser, Unicode, canonical message, tampered-content and malformed-input checks passed.")
