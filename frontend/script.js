document.addEventListener('DOMContentLoaded', () => {
    // Tab switching logic
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            tab.classList.add('active');
            const targetId = tab.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });

    // Dynamic inputs logic
    const sourcesList = document.getElementById('sources-list');
    const addSourceBtn = document.getElementById('add-source-btn');

    addSourceBtn.addEventListener('click', () => {
        const row = document.createElement('div');
        row.className = 'input-row';
        row.innerHTML = `
            <input type="text" class="source-path" placeholder="/home/user/documents/cv..." required />
            <button type="button" class="btn-icon remove-btn" aria-label="Remove path">×</button>
        `;
        sourcesList.appendChild(row);

        row.querySelector('.remove-btn').addEventListener('click', () => row.remove());
    });

    // Toggle PDF fields visibility
    const pdfCheck = document.getElementById('exportPdfCheck');
    const pdfFields = document.getElementById('pdf-fields-container');
    if (pdfCheck) {
        pdfCheck.addEventListener('change', () => {
            if (pdfCheck.checked) {
                pdfFields.classList.remove('hidden');
            } else {
                pdfFields.classList.add('hidden');
            }
        });
    }

    // Form Submitting & Canvas Init
    const form = document.getElementById('job-form');
    const formContainer = document.getElementById('job-form');
    const submitBtn = document.getElementById('generate-btn');
    const btnText = document.querySelector('.btn-text');
    const loader = document.querySelector('.loader');
    
    const textResult = document.getElementById('text-result');
    const letterOutput = document.getElementById('letter-output');
    const resultMeta = document.getElementById('result-meta');
    const copyLetterBtn = document.getElementById('copy-letter-btn');

    let currentCompanySlug = "company";
    let selectedOutputDir = "";

    copyLetterBtn.addEventListener('click', async () => {
        const letter = letterOutput.textContent || '';
        if (!letter) {
            return;
        }

        try {
            await navigator.clipboard.writeText(letter);
            copyLetterBtn.textContent = 'Copied';
            window.setTimeout(() => {
                copyLetterBtn.textContent = 'Copy Text';
            }, 1200);
        } catch (error) {
            console.error('Clipboard error:', error);
            alert('Could not copy the cover letter text.');
        }
    });

    // Load defaults from localStorage
    if (localStorage.getItem('jh_name')) document.getElementById('nameInput').value = localStorage.getItem('jh_name');
    if (localStorage.getItem('jh_contact')) document.getElementById('contactInput').value = localStorage.getItem('jh_contact');
    if (localStorage.getItem('jh_role')) document.getElementById('roleInput').value = localStorage.getItem('jh_role');
    if (localStorage.getItem('jh_outdir')) document.getElementById('outDirInput').value = localStorage.getItem('jh_outdir');
    
    try {
        const savedSources = JSON.parse(localStorage.getItem('jh_sources'));
        if (savedSources && savedSources.length > 0) {
            sourcesList.innerHTML = '';
            savedSources.forEach(src => {
                const row = document.createElement('div');
                row.className = 'input-row';
                row.innerHTML = `
                    <input type="text" class="source-path" value="${src}" placeholder="/home/user/documents/cv..." required />
                    <button type="button" class="btn-icon remove-btn" aria-label="Remove path">×</button>
                `;
                sourcesList.appendChild(row);
                row.querySelector('.remove-btn').addEventListener('click', () => row.remove());
            });
        }
    } catch(e) { console.error('Error loading sources:', e); }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Gather data
        const activeTab = document.querySelector('.tab.active').getAttribute('data-target');
        const jobUrl = activeTab === 'job-url' ? document.getElementById('urlInput').value.trim() : null;
        const jobDesc = activeTab === 'job-desc' ? document.getElementById('descInput').value.trim() : null;
        const role = document.getElementById('roleInput').value.trim();
        const model = document.getElementById('modelInput').value.trim() || 'gemma4:latest';
        
        // Output and PDF options
        const outDir = document.getElementById('outDirInput').value.trim();
        const exportPdf = document.getElementById('exportPdfCheck').checked;
        const candidateName = document.getElementById('nameInput').value.trim() || "Jane Doe";
        const candidateContact = document.getElementById('contactInput').value.trim() || "jane.doe@example.com";

        const sources = Array.from(document.querySelectorAll('.source-path'))
                             .map(input => input.value.trim())
                             .filter(value => value !== '');

        if (sources.length === 0) {
            alert("Please provide at least one source directory or URL.");
            return;
        }

        if (!jobUrl && !jobDesc) {
            alert("Please provide either a Job URL or a Job Description.");
            return;
        }

        // Save to localStorage
        localStorage.setItem('jh_name', candidateName);
        localStorage.setItem('jh_contact', candidateContact);
        localStorage.setItem('jh_role', role);
        localStorage.setItem('jh_outdir', outDir);
        localStorage.setItem('jh_sources', JSON.stringify(sources));

        submitBtn.disabled = true;
        btnText.textContent = 'Generating...';
        loader.classList.remove('hidden');
        textResult.classList.add('hidden');
        resultMeta.classList.add('hidden');

        try {
            const body = {
                sources_dir: sources,
                job_url: jobUrl,
                job_text: jobDesc,
                role: role,
                model: model,
                keep_alive: '10m',
                output_dir: outDir,
                save_as_pdf: exportPdf,
                candidate_name: candidateName,
                candidate_contact: candidateContact
            };

            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'An unexpected error occurred');
            }

            const data = await response.json();
            
            // Extract company logic implicitly if the JSON adds it, otherwise default.
            currentCompanySlug = "company";
            selectedOutputDir = outDir;
            
            if (exportPdf) {
                if (!data.saved_path || !data.download_url) {
                    throw new Error('PDF was generated but no file was returned by the server.');
                }

                const pdfWindow = window.open(data.download_url, '_blank', 'noopener');
                if (!pdfWindow) {
                    window.location.href = data.download_url;
                }
            } else {
                letterOutput.textContent = data.letter || '';
                textResult.classList.remove('hidden');

                if (data.saved_path) {
                    resultMeta.innerHTML = `<strong>Saved text copy:</strong> ${data.saved_path}`;
                    resultMeta.classList.remove('hidden');
                }
            }

        } catch (error) {
            console.error('Error:', error);
            alert(`Generation failed: ${error.message}`);
        } finally {
            submitBtn.disabled = false;
            btnText.textContent = 'Generate Cover Letter';
            loader.classList.add('hidden');
        }
    });

});
