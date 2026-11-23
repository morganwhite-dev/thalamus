// Thalamus: a plain window around the local dashboard (http://127.0.0.1:8765/).
// The dashboard server is kept running by launchd; this app only shows it. No data of its own.
import Cocoa
import WebKit

let url = URL(string: "http://127.0.0.1:8765/")!

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, NSWindowDelegate {
    var window: NSWindow!
    var web: WKWebView!        // the dashboard
    var welcome: WKWebView!    // the welcome overlay, shown on top until the dashboard is ready
    var retry: Timer?
    var downSince: Date?
    let userName = "Morgan"
    let minWelcome: TimeInterval = 7.0      // the welcome stays at least this long
    let settle: TimeInterval = 1.8          // after the dashboard loads, let its brain draw before fading
    let fadeSeconds: TimeInterval = 1.6
    var shownAt = Date()
    var loading = false
    var overlayUp = true

    func applicationDidFinishLaunching(_ n: Notification) {
        let bg = NSColor(red: 0.02, green: 0.025, blue: 0.06, alpha: 1)
        web = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        web.navigationDelegate = self
        web.uiDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        web.configuration.userContentController.addUserScript(WKUserScript(source: "window.THALAMUS_APP=true; window.THALAMUS_PAD=0", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        welcome = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        welcome.setValue(false, forKey: "drawsBackground")
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Thalamus"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.backgroundColor = bg
        let box = NSView(); box.wantsLayer = true; box.layer?.backgroundColor = bg.cgColor
        for v in [web!, welcome!] { v.frame = box.bounds; v.autoresizingMask = [.width, .height]; box.addSubview(v) }
        window.contentView = box
        window.setFrameAutosaveName("ThalamusMain")
        if !window.setFrameUsingName("ThalamusMain") { window.center() }
        window.delegate = self
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        buildMenu()
        showWelcome()
    }

    func load() { web.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)) }

    func showWelcome() {
        shownAt = Date(); downSince = nil; loading = false; overlayUp = true
        welcome.isHidden = false
        welcome.alphaValue = 1
        web.alphaValue = 0
        welcome.loadHTMLString(welcomeHTML(name: userName), baseURL: URL(string: "https://fonts.googleapis.com"))
        probe()
    }

    // Wait for the dashboard server, load the dashboard quietly behind the welcome, then crossfade.
    func probe() {
        var req = URLRequest(url: url); req.timeoutInterval = 2; req.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: req) { [weak self] _, resp, _ in
            DispatchQueue.main.async {
                guard let self = self, self.overlayUp, !self.loading else { return }
                if (resp as? HTTPURLResponse)?.statusCode == 200 { self.loading = true; self.load() } else { self.stillDown() }
            }
        }.resume()
    }

    func stillDown() {
        if downSince == nil { downSince = Date() }
        if Date().timeIntervalSince(downSince!) > 30 {
            welcome.evaluateJavaScript("document.getElementById('st').textContent='// server not answering on :8765'")
        }
        retry?.invalidate()
        retry = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: false) { [weak self] _ in self?.probe() }
    }

    func reveal() {
        guard overlayUp else { return }
        overlayUp = false
        let wait = max(settle, minWelcome - Date().timeIntervalSince(shownAt))
        DispatchQueue.main.asyncAfter(deadline: .now() + wait) { [weak self] in
            guard let self = self else { return }
            self.welcome.evaluateJavaScript("document.body.classList.add('out')")   // softly dims the logo too
            self.web.evaluateJavaScript("window.THALAMUS_REVEALED=true; window.thalamusReveal && window.thalamusReveal()")   // the hologram plays its intro now
            NSAnimationContext.runAnimationGroup({ ctx in
                ctx.duration = self.fadeSeconds
                ctx.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                self.web.animator().alphaValue = 1
                self.welcome.animator().alphaValue = 0
            }, completionHandler: { [weak self] in
                self?.welcome.isHidden = true                 // a faded view still catches clicks unless it is hidden
                self?.window.makeFirstResponder(self?.web)
            })
        }
    }

    func webView(_ w: WKWebView, didFailProvisionalNavigation n: WKNavigation!, withError e: Error) {
        loading = false
        if !overlayUp { showWelcome() } else { stillDown() }     // the server went away: bring the welcome back
    }
    func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
        if w.url?.host == "127.0.0.1" { downSince = nil; setPad(0); if overlayUp { reveal() } }
    }

    // Links that leave the dashboard open in the normal browser.
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = a.request.url, let host = u.host, host != "127.0.0.1", a.navigationType == .linkActivated {
            NSWorkspace.shared.open(u); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }
    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { NSWorkspace.shared.open(u) }
        return nil
    }
    // Plain confirm/alert/prompt dialogs (the Plain page uses them).
    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = m; a.runModal(); completionHandler()
    }
    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = m; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        completionHandler(a.runModal() == .alertFirstButtonReturn)
    }
    func webView(_ w: WKWebView, runJavaScriptTextInputPanelWithPrompt p: String, defaultText d: String?, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert(); a.messageText = p; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        let t = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24)); t.stringValue = d ?? ""; a.accessoryView = t
        completionHandler(a.runModal() == .alertFirstButtonReturn ? t.stringValue : nil)
    }

    func setPad(_ px: Int) { web.evaluateJavaScript("window.THALAMUS_PAD=\(px); window.thalamusPad && window.thalamusPad(\(px))") }
    func windowWillEnterFullScreen(_ n: Notification) { setPad(0) }       // no window buttons in full screen
    func windowDidExitFullScreen(_ n: Notification) { setPad(0) }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows f: Bool) -> Bool { window.makeKeyAndOrderFront(nil); return true }

    @objc func reload() { if overlayUp { showWelcome() } else { load() } }

    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let app = NSMenu(); appItem.submenu = app
        app.addItem(withTitle: "Quit Thalamus", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let view = NSMenu(title: "View"); viewItem.submenu = view
        view.addItem(withTitle: "Reload", action: #selector(reload), keyEquivalent: "r")
        view.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f").keyEquivalentModifierMask = [.command, .control]
        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Edit"); editItem.submenu = edit
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
