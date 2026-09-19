import AppKit
import Foundation

@MainActor
final class ReviewApp: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var request: ReviewRequest?
    var requestURL: URL?
    var outputURL: URL!
    var enroll = false
    let signer = EnclaveSigner()
    var approve: NSButton!
    var confirmation: NSButton!

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let args = Array(CommandLine.arguments.dropFirst())
            if args.count == 2 && args[0] == "--enroll" {
                enroll = true
                outputURL = URL(fileURLWithPath: args[1])
            } else if args.count == 4 && args[0] == "--review" && args[2] == "--receipt" {
                requestURL = URL(fileURLWithPath: args[1])
                request = try ReviewRequest(data: Data(contentsOf: requestURL!))
                outputURL = URL(fileURLWithPath: args[3])
            } else {
                throw ApprovalError(message: "Usage: VaultApproval --enroll PUBLIC_KEY.json\nor VaultApproval --review REQUEST.json --receipt RECEIPT.json")
            }
            guard !FileManager.default.fileExists(atPath: outputURL.path) else {
                throw ApprovalError(message: "Output already exists. Choose a new output path; receipts and key exports are never overwritten.")
            }
            window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1050, height: 760),
                              styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            window.title = enroll ? "Set up vault approval" : "Review vault batch — no changes applied"
            let stack = NSStackView()
            stack.orientation = .vertical
            stack.spacing = 12
            stack.edgeInsets = NSEdgeInsets(top: 16, left: 16, bottom: 16, right: 16)
            let scroll = NSScrollView()
            scroll.hasVerticalScroller = true
            scroll.hasHorizontalScroller = true
            let text = NSTextView(frame: NSRect(x: 0, y: 0, width: 990, height: 650))
            text.isEditable = false
            text.isSelectable = true
            text.isRichText = false
            text.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
            text.autoresizingMask = [.width]
            text.textContainer?.widthTracksTextView = true
            text.string = enroll ? "Set up owner approval\n\nThis creates a device-bound Secure Enclave signing key. Signing requires macOS owner authentication. There is no software-key fallback.\n\nOnly the public key will be exported to:\n\(outputURL.path)\n\nNo vault configuration, note or proposal is changed. Keep the private key envelope in Application Support/VaultApproval. It cannot be used on another device.\n\nEnroll before generating your final proposal; changing its configured public key invalidates existing proposals." : request!.reviewText
            scroll.documentView = text
            stack.addArrangedSubview(scroll)
            confirmation = NSButton(checkboxWithTitle: enroll ? "I want to enroll this Mac for approvals" : "I reviewed every affected file and the source/grounding metadata", target: self, action: #selector(toggle))
            stack.addArrangedSubview(confirmation)
            let buttons = NSStackView()
            let cancel = NSButton(title: "Cancel — approve nothing", target: self, action: #selector(cancel))
            approve = NSButton(title: enroll ? "Enroll and export public key" : "Approve this exact batch…", target: self, action: #selector(approveBatch))
            approve.isEnabled = false
            buttons.addArrangedSubview(cancel)
            buttons.addArrangedSubview(approve)
            stack.addArrangedSubview(buttons)
            window.contentView = stack
            window.center()
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        } catch { fail(error, terminate: true) }
    }
    @objc func toggle() { approve.isEnabled = confirmation.state == .on }
    @objc func cancel() { NSApp.terminate(nil) }
    @objc func approveBatch() {
        approve.isEnabled = false
        do {
            if enroll {
                try signer.enroll(export: outputURL)
            } else {
                guard try Data(contentsOf: requestURL!) == request!.original else {
                    throw ApprovalError(message: "The request changed after opening. Reopen and review it again.")
                }
                let receipt = try signer.sign(request!)
                guard try Data(contentsOf: requestURL!) == request!.original else {
                    throw ApprovalError(message: "The request changed during approval. No receipt was saved.")
                }
                try receipt.write(to: outputURL, options: .withoutOverwriting)
                try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: outputURL.path)
            }
            let alert = NSAlert()
            alert.messageText = enroll ? "Public key exported" : "Approval receipt saved — no vault files changed"
            alert.informativeText = outputURL.path
            alert.runModal()
            NSApp.terminate(nil)
        } catch {
            fail(error, terminate: false)
            approve.isEnabled = confirmation.state == .on
        }
    }
    func fail(_ error: Error, terminate: Bool) {
        let alert = NSAlert()
        alert.messageText = "Nothing approved"
        alert.informativeText = error.localizedDescription
        alert.runModal()
        if terminate { NSApp.terminate(nil) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

if CommandLine.arguments.contains("--help") {
    print("VaultApproval --enroll PUBLIC_KEY.json\nVaultApproval --review REQUEST.json --receipt RECEIPT.json\nOwner authentication is required. This app never writes vault files.")
} else {
    let app = NSApplication.shared
    let delegate = ReviewApp()
    app.setActivationPolicy(.regular)
    app.delegate = delegate
    app.run()
}
