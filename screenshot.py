from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1200, 'height': 900})
        page.goto('http://localhost:8000')
        
        # 1. Take screenshot of Form View
        page.screenshot(path='assets/frontend_form.png', full_page=True)
        
        # 2. Trigger dummy canvas rendering directly via DOM to bypass Ollama inference
        page.evaluate('''() => {
            document.getElementById('job-form').classList.add('hidden');
            document.getElementById('editor-container').classList.remove('hidden');
            
            const canvas = document.getElementById('pdf-canvas');
            canvas.innerHTML = `
                <div class="draggable-block" draggable="true" style="text-align: center;">
                    <button class="block-delete-btn" contenteditable="false" aria-label="Delete block" style="display: flex;">×</button>
                    <div contenteditable="true" style="outline:none; border: 2px dashed rgba(99, 102, 241, 0.4); padding: 5px;">
                        <div style="font-size: 1.5em; font-weight: bold;">Jane Doe</div>
                        <div style="font-size: 0.9em; opacity: 0.8; margin-top: 5px;">jane@example.com / 555-0100</div>
                    </div>
                </div>
                <div class="draggable-block" draggable="true" style="text-align: left;">
                    <button class="block-delete-btn" contenteditable="false" aria-label="Delete block">×</button>
                    <div contenteditable="true" style="outline:none;">
                        <div style="margin-top: 15px;">April 14, 2026</div>
                    </div>
                </div>
                <div class="draggable-block" draggable="true" style="text-align: left;">
                    <button class="block-delete-btn" contenteditable="false" aria-label="Delete block">×</button>
                    <div contenteditable="true" style="outline:none;">
                        <div style="margin-top: 1em;">Dear Hiring Manager,</div>
                    </div>
                </div>
                <div class="draggable-block" draggable="true" style="text-align: left;">
                    <button class="block-delete-btn" contenteditable="false" aria-label="Delete block">×</button>
                    <div contenteditable="true" style="outline:none;">
                        <div style="margin-top: 1em;">I am writing to express my strong interest in the Software Engineering position. As an experienced developer with a passion for scalable web architectures, I believe my background aligns perfectly with your team's objectives.</div>
                    </div>
                </div>
                <div class="draggable-block" draggable="true" style="text-align: left;">
                    <button class="block-delete-btn" contenteditable="false" aria-label="Delete block">×</button>
                    <div contenteditable="true" style="outline:none;">
                        <div style="margin-top: 1em;">Best regards,<br>Jane Doe</div>
                    </div>
                </div>
            `;
        }''')
        
        page.wait_for_timeout(1000)
        
        # 3. Take screenshot of Editor View
        page.screenshot(path='assets/frontend_canvas.png', full_page=True)
        
        browser.close()

if __name__ == '__main__':
    run()
