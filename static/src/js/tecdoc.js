document.addEventListener('DOMContentLoaded', () => {
    const modeBtns = document.querySelectorAll('.mode-btn');
    const quickSearchUI = document.getElementById('quickSearchUI');
    const vehicleSearchUI = document.getElementById('vehicleSearchUI');

    const typeBtns = document.querySelectorAll('.type-btn');
    const searchInput = document.getElementById('searchInput');

    const makeSelect = document.getElementById('makeSelect');
    const modelSelect = document.getElementById('modelSelect');
    const engineSelect = document.getElementById('engineSelect');
    const categorySelect = document.getElementById('categorySelect');

    const submitBtn = document.getElementById('submitBtn');
    const spinner = document.getElementById('spinner');
    const btnText = document.getElementById('btnText');
    const resultsContainer = document.getElementById('resultsContainer');

    let currentMode = 'quick';
    let currentSearchType = 'text';

    // switch between quick and vehicle search mode
    modeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            modeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentMode = btn.dataset.mode;

            if (currentMode === 'quick') {
                quickSearchUI.style.display = 'block';
                vehicleSearchUI.style.display = 'none';
            } else {
                quickSearchUI.style.display = 'none';
                vehicleSearchUI.style.display = 'block';
                if (makeSelect.options.length <= 1) {
                    loadMakes(); // Load makes the first time we enter Vehicle Search
                }
            }
        });
    });

    // update placeholder text based on selected search type
    typeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            typeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentSearchType = btn.dataset.type;

            if (currentSearchType === 'vin') searchInput.placeholder = 'Enter 17-digit VIN (e.g. 1HGBH41JXMN109186)...';
            else if (currentSearchType === 'part_number') searchInput.placeholder = 'Enter exact part number (e.g. 0986494300)...';
            else if (currentSearchType === 'oem_number') searchInput.placeholder = 'Enter OEM number (e.g. 4B0698151E)...';
            else if (currentSearchType === 'engine_code') searchInput.placeholder = 'Enter engine code (e.g. AWX, BKD, 2JZ-GTE)...';
            else searchInput.placeholder = 'Enter part name or article number...';
        });
    });

    async function fetchDropdownData(endpoint, params = {}) {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params })
            });
            const rpc = await response.json();
            if (rpc.error) throw new Error(rpc.error.data?.message || 'Server Error');
            if (rpc.result && rpc.result.status === 200) return rpc.result.data;
            throw new Error(rpc.result?.message || 'Failed to fetch data');
        } catch (e) {
            console.error(e);
            return [];
        }
    }

    function populateSelect(selectElement, items, defaultText) {
        selectElement.innerHTML = `<option value="">${defaultText}</option>`;

        // Ensure items is an array, as RapidAPI might return nested objects depending on endpoint
        let list = [];
        if (Array.isArray(items)) {
            list = items;
        } else if (items && typeof items === 'object') {
            // Try to find the first array inside the object
            const possibleArray = Object.values(items).find(val => Array.isArray(val));
            if (possibleArray) {
                list = possibleArray;
            } else {
                list = [items];
            }
        }

        list.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.categoryId1 || item.assemblyGroupNodeId || item.categoryId || item.id || item.vehicleId || item.carId || item.modelId || item.manufacturerId || item.manuId || item.engineId;
            opt.textContent = item.categoryName1 || item.assemblyGroupName || item.categoryName || item.name || item.typeEngineName || item.carName || item.vehicleName || item.modelName || item.manufacturerName || item.manuName || item.description || item.assemblyGroup;
            selectElement.appendChild(opt);
        });
        selectElement.disabled = list.length === 0;
    }

    async function loadMakes() {
        makeSelect.innerHTML = '<option value="">Loading Makes...</option>';
        makeSelect.disabled = true;
        const makes = await fetchDropdownData('/api/tecdoc/manufacturers');
        populateSelect(makeSelect, makes, '1. Select Make');
    }

    makeSelect.addEventListener('change', async () => {
        modelSelect.innerHTML = '<option value="">Loading Models...</option>';
        modelSelect.disabled = true;
        engineSelect.innerHTML = '<option value="">3. Select Engine</option>';
        engineSelect.disabled = true;
        categorySelect.innerHTML = '<option value="">4. Select Category (Optional)</option>';
        categorySelect.disabled = true;

        if (!makeSelect.value) {
            populateSelect(modelSelect, [], '2. Select Model');
            return;
        }
        const models = await fetchDropdownData('/api/tecdoc/models', { brand_id: makeSelect.value });
        populateSelect(modelSelect, models, '2. Select Model');
    });

    modelSelect.addEventListener('change', async () => {
        engineSelect.innerHTML = '<option value="">Loading Engines...</option>';
        engineSelect.disabled = true;
        categorySelect.innerHTML = '<option value="">4. Select Category (Optional)</option>';
        categorySelect.disabled = true;

        if (!modelSelect.value) {
            populateSelect(engineSelect, [], '3. Select Engine');
            return;
        }
        const engines = await fetchDropdownData('/api/tecdoc/engines', { brand_id: makeSelect.value, model_id: modelSelect.value });
        populateSelect(engineSelect, engines, '3. Select Engine');
    });

    engineSelect.addEventListener('change', async () => {
        categorySelect.innerHTML = '<option value="">Loading Categories...</option>';
        categorySelect.disabled = true;

        if (!engineSelect.value) {
            populateSelect(categorySelect, [], '4. Select Category (Optional)');
            return;
        }
        const categories = await fetchDropdownData('/api/tecdoc/categories', { vehicle_id: engineSelect.value });
        populateSelect(categorySelect, categories, '4. Select Category (Required)');
    });

    // main search handler
    const executeSearchApi = async (searchType, query, kwargs = {}) => {
        submitBtn.disabled = true;
        spinner.style.display = 'block';
        btnText.textContent = 'Searching...';
        resultsContainer.style.display = 'flex';
        resultsContainer.innerHTML = `
            <div class="status-message">
                Connecting to RapidAPI Auto Parts Catalog...
            </div>
        `;

        try {
            const response = await fetch('/api/tecdoc/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: { search_type: searchType, query: query, ...kwargs }
                })
            });

            const rpcResponse = await response.json();
            if (rpcResponse.error) throw new Error(rpcResponse.error.data?.message || 'Server Error');
            const data = rpcResponse.result;
            if (!data) throw new Error("No response received from server");
            if (data.status === 429) {
                resultsContainer.innerHTML = `<div class="status-message" style="color:#e67e22;">
                    ⚠️ <strong>Monthly API Quota Exceeded</strong><br><br>
                    You have used all your RapidAPI requests for this month.<br>
                    Please <a href="https://rapidapi.com/makingdatameaningful/api/auto-parts-catalog" target="_blank">upgrade your plan</a> to continue searching.
                </div>`;
                return;
            }
            if (data.status !== 200) throw new Error(data.message || data.error || "Search failed");

            // vin search: parse response and auto-populate vehicle dropdowns
            if (searchType === 'vin' && data.data && data.data.matchingManufacturers?.array?.length > 0) {
                const manuId = data.data.matchingManufacturers.array[0].manuId;
                const manuName = data.data.matchingManufacturers.array[0].manuName;
                const modelId = data.data.matchingModels?.array?.[0]?.modelId;
                const modelName = data.data.matchingModels?.array?.[0]?.modelName;
                // matchingVehicles can be an empty string "" or an object with array key
                const vehiclesArr = Array.isArray(data.data.matchingVehicles?.array) ? data.data.matchingVehicles.array : [];
                const vehicleId = vehiclesArr[0]?.vehicleId || vehiclesArr[0]?.carId;
                const vehicleName = vehiclesArr[0]?.carName;
                // Rich data from decoder-v2
                const decoder = data.decoder || {};
                const decoderInfo = decoder.make ? `
                    <table style="margin-top:10px;border-collapse:collapse;width:100%;">
                        <tr><td style="padding:3px 8px;"><b>Make:</b></td><td>${decoder.make || ''}</td><td style="padding:3px 8px;"><b>Model:</b></td><td>${decoder.model || ''}</td></tr>
                        <tr><td style="padding:3px 8px;"><b>Year:</b></td><td>${decoder.model_year || ''}</td><td style="padding:3px 8px;"><b>Trim:</b></td><td>${decoder.trim || ''}</td></tr>
                        <tr><td style="padding:3px 8px;"><b>Engine:</b></td><td>${decoder['displacement_(l)'] ? decoder['displacement_(l)'] + 'L' : ''} ${decoder.engine_configuration || ''} ${decoder.engine_number_of_cylinders ? decoder.engine_number_of_cylinders + '-cyl' : ''}</td><td style="padding:3px 8px;"><b>Fuel:</b></td><td>${decoder['fuel_type_-_primary'] || ''}</td></tr>
                        <tr><td style="padding:3px 8px;"><b>Country:</b></td><td>${decoder.plant_country || ''}</td><td style="padding:3px 8px;"><b>Type:</b></td><td>${decoder.vehicle_type || ''}</td></tr>
                    </table>` : '';

                if (manuId) {
                    // Switch to vehicle search tab — find the mode button by data attribute
                    const vehicleModeBtn = document.querySelector('.mode-btn[data-mode="vehicle"]');
                    if (vehicleModeBtn) {
                        modeBtns.forEach(b => b.classList.remove('active'));
                        vehicleModeBtn.classList.add('active');
                        currentMode = 'vehicle';
                        quickSearchUI.style.display = 'none';
                        vehicleSearchUI.style.display = 'block';
                    }

                    let message = `<strong>VIN Decoded Successfully!</strong><br><br>Auto-populating Vehicle Search for: <b>`;

                    // Auto-fill Make
                    makeSelect.value = manuId;
                    const models = await fetchDropdownData('/api/tecdoc/models', { brand_id: manuId });
                    populateSelect(modelSelect, models, '2. Select Model');

                    if (modelId) {
                        message += `${modelName}`;
                        modelSelect.value = modelId;
                        modelSelect.disabled = false;

                        const engines = await fetchDropdownData('/api/tecdoc/engines', { brand_id: manuId, model_id: modelId });
                        populateSelect(engineSelect, engines, '3. Select Engine');

                        if (vehicleId) {
                            message += ` -> ${vehicleName}</b>`;
                            engineSelect.value = vehicleId;
                            engineSelect.disabled = false;

                            const categories = await fetchDropdownData('/api/tecdoc/categories', { vehicle_id: vehicleId });
                            populateSelect(categorySelect, categories, '4. Select Category (Required)');
                            categorySelect.disabled = false;
                        } else {
                            message += `</b><br><br><span style="color:var(--text-color); font-weight:normal;">RapidAPI matched the Model, but couldn't identify the exact Engine variant. Please select your Engine manually from the dropdown.</span>`;
                        }
                    } else {
                        message += `${manuName}</b><br><br><span style="color:var(--text-color); font-weight:normal;">RapidAPI matched the Manufacturer, but couldn't identify the exact Model. Please select your Model manually.</span>`;
                        modelSelect.disabled = false;
                    }

                    resultsContainer.innerHTML = `
                        <div class="status-message" style="color:var(--success); border-color:var(--success);">
                            ${message}
                            ${decoderInfo}
                        </div>
                    `;
                    return;
                }
            }

            renderResults(data.data);
        } catch (error) {
            resultsContainer.innerHTML = `
                <div class="status-message error-message">
                    <strong>Error:</strong> ${error.message}
                </div>
            `;
        } finally {
            submitBtn.disabled = false;
            spinner.style.display = 'none';
            btnText.textContent = 'Search';
        }
    };

    const performSearch = () => {
        if (currentMode === 'quick') {
            const query = searchInput.value.trim();
            if (!query) return alert('Please enter a search query');
            executeSearchApi(currentSearchType, query);
        } else {
            if (!makeSelect.value || !modelSelect.value || !engineSelect.value || !categorySelect.value) {
                return alert('Please select a Make, Model, Engine, and Category first!');
            }
            executeSearchApi('exact_vehicle', '', {
                brand_id: makeSelect.value,
                model_id: modelSelect.value,
                vehicle_id: engineSelect.value,
                category_id: categorySelect.value, // Required
                vehicle_name: engineSelect.options[engineSelect.selectedIndex].text
            });
        }
    };

    submitBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') performSearch();
    });

    // expose findAlternatives globally for inline onclick calls
    window.findAlternatives = (articleId) => {
        if (!articleId) {
            resultsContainer.innerHTML = `<div class="status-message error-message"><strong>Error:</strong> No article ID available to find alternatives for.</div>`;
            return;
        }
        // Switch to Quick Search mode so the result renders correctly
        const quickModeBtn = document.querySelector('.mode-btn[data-mode="quick"]');
        if (quickModeBtn && currentMode !== 'quick') {
            modeBtns.forEach(b => b.classList.remove('active'));
            quickModeBtn.classList.add('active');
            currentMode = 'quick';
            quickSearchUI.style.display = 'block';
            vehicleSearchUI.style.display = 'none';
        }
        searchInput.value = `Alternatives for: ${articleId}`; // Visual feedback
        executeSearchApi('alternatives', articleId);
    };

    // pagination state
    const PAGE_SIZE = 5;
    let _allResults = [];
    let _currentPage = 0;

    function buildCard(item, index) {
        const card = document.createElement('div');
        card.className = 'result-card';
        card.style.animationDelay = `${(index % PAGE_SIZE) * 0.08}s`;

        const brand = item.brandName || item.mfrName || item.supplierName || item.brand || item.mfrId || 'Unknown Brand';
        const articleNo = item.articleNo || item.partNumber || item.articleNumber || 'N/A';
        const genericName = item.genericArticleName || item.articleProductName || item.name || item.description || 'Auto Part';

        let imagesHtml = '';
        const images = item.images || item.articleImages || item.media || (item.s3image ? [{ url: item.s3image }] : []);
        if (images.length > 0) {
            imagesHtml = '<div class="images-gallery" style="display:flex;gap:1rem;overflow-x:auto;margin-bottom:1.5rem;padding-bottom:0.5rem;">';
            images.forEach(img => {
                const url = img.imageURL800 || img.imageURL400 || img.imageURL || img.url || img.imageURL200 || (typeof img === 'string' ? img : '');
                if (url) imagesHtml += `<img src="${url}" alt="Part Image" style="height:160px;border-radius:0.5rem;object-fit:cover;border:1px solid var(--border-color);box-shadow:0 4px 6px rgba(0,0,0,0.3);"/>`;
            });
            imagesHtml += '</div>';
        }

        let detailsHtml = '<div class="details-grid">';
        if (item.status) detailsHtml += `<div class="detail-item"><span class="detail-label">Status</span><span class="detail-value">${item.status}</span></div>`;
        if (item.eanNumber || item.ean) detailsHtml += `<div class="detail-item"><span class="detail-label">EAN Number</span><span class="detail-value">${item.eanNumber || item.ean}</span></div>`;
        detailsHtml += '</div>';

        const rawJson = JSON.stringify(item, null, 2);
        const internalArticleId = item.articleId || item.id || item.legacyArticleId || '';
        const alternativeBtn = internalArticleId
            ? `<button class="btn-secondary" onclick="window.findAlternatives('${internalArticleId}')">
                <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M11.5 15a.5.5 0 0 0 .5-.5V2.707l3.146 3.147a.5.5 0 0 0 .708-.708l-4-4a.5.5 0 0 0-.708 0l-4 4a.5.5 0 1 0 .708.708L11 2.707V14.5a.5.5 0 0 0 .5.5zm-7-14a.5.5 0 0 1 .5.5v11.793l3.146-3.147a.5.5 0 0 1 .708.708l-4 4a.5.5 0 0 1-.708 0l-4-4a.5.5 0 0 1 .708-.708L4 13.293V1.5a.5.5 0 0 1 .5-.5z"/></svg>
                Find Alternatives
               </button>`
            : '';

        card.innerHTML = `
            <div class="result-header">
                <div class="brand-name">${brand} - ${genericName}</div>
                <div class="article-no"># ${articleNo}</div>
            </div>
            ${imagesHtml}
            ${detailsHtml}
            <div>${alternativeBtn}</div>
            <details style="margin-top:1.5rem;cursor:pointer;padding-top:1rem;border-top:1px solid var(--border-color);">
                <summary style="color:var(--text-muted);font-size:0.9rem;outline:none;display:flex;align-items:center;gap:0.5rem;">
                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M10.478 1.647a.5.5 0 1 0-.956-.294l-4 13a.5.5 0 0 0 .956.294l4-13zM4.854 4.146a.5.5 0 0 1 0 .708L1.707 8l3.147 3.146a.5.5 0 0 1-.708.708l-3.5-3.5a.5.5 0 0 1 0-.708l3.5-3.5a.5.5 0 0 1 .708 0zm6.292 0a.5.5 0 0 0 0 .708L14.293 8l-3.147 3.146a.5.5 0 0 0 .708.708l3.5-3.5a.5.5 0 0 0 0-.708l-3.5-3.5a.5.5 0 0 0-.708 0z"/></svg>
                    View Raw Data Payload
                </summary>
                <pre>${rawJson}</pre>
            </details>
        `;
        return card;
    }

    function renderPage(startIndex) {
        // Remove existing Load-More button so we can reinsert it at the bottom
        const existingBtn = document.getElementById('loadMoreBtn');
        if (existingBtn) existingBtn.remove();

        const slice = _allResults.slice(startIndex, startIndex + PAGE_SIZE);
        slice.forEach((item, i) => {
            resultsContainer.appendChild(buildCard(item, startIndex + i));
        });

        const rendered = startIndex + slice.length;
        const remaining = _allResults.length - rendered;

        if (remaining > 0) {
            const loadMoreWrapper = document.createElement('div');
            loadMoreWrapper.id = 'loadMoreBtn';
            loadMoreWrapper.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:0.6rem;margin-top:1.5rem;padding-bottom:2rem;';
            loadMoreWrapper.innerHTML = `
                <button id="loadMoreInner" style="
                    display:flex;align-items:center;gap:0.6rem;
                    padding:0.7rem 2rem;border-radius:999px;border:none;cursor:pointer;
                    background:linear-gradient(135deg,var(--accent,#6c63ff),var(--accent-alt,#a78bfa));
                    color:#fff;font-size:0.95rem;font-weight:600;letter-spacing:0.02em;
                    box-shadow:0 4px 18px rgba(108,99,255,0.35);
                    transition:transform 0.18s,box-shadow 0.18s;
                " onmouseover="this.style.transform='scale(1.04)';this.style.boxShadow='0 6px 24px rgba(108,99,255,0.5)';"
                   onmouseout="this.style.transform='scale(1)';this.style.boxShadow='0 4px 18px rgba(108,99,255,0.35)';">
                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                        <path fill-rule="evenodd" d="M1.5 8a6.5 6.5 0 1 1 13 0 6.5 6.5 0 0 1-13 0zM8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm.5 4.5a.5.5 0 0 0-1 0v3h-3a.5.5 0 0 0 0 1h3v3a.5.5 0 0 0 1 0v-3h3a.5.5 0 0 0 0-1h-3v-3z"/>
                    </svg>
                    Load More
                </button>
                <span style="color:var(--text-muted);font-size:0.82rem;">
                    Showing <strong style="color:var(--text-color)">${rendered}</strong> of
                    <strong style="color:var(--text-color)">${_allResults.length}</strong> results
                    &nbsp;·&nbsp;
                    <strong style="color:var(--accent,#6c63ff)">${remaining}</strong> remaining
                </span>
            `;
            resultsContainer.appendChild(loadMoreWrapper);

            document.getElementById('loadMoreInner').addEventListener('click', () => {
                _currentPage++;
                renderPage(_currentPage * PAGE_SIZE);
                // Smooth-scroll so new cards are in view
                loadMoreWrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        } else {
            // All results shown — show a subtle "end of results" pill
            const doneEl = document.createElement('div');
            doneEl.style.cssText = 'text-align:center;color:var(--text-muted);font-size:0.82rem;margin-top:1.5rem;padding-bottom:2rem;';
            doneEl.innerHTML = `✓ All <strong style="color:var(--text-color)">${_allResults.length}</strong> results loaded`;
            resultsContainer.appendChild(doneEl);
        }
    }

    function renderResults(items) {
        // --- Normalise raw API data into a flat array ---
        let list = [];
        if (Array.isArray(items)) {
            list = items;
        } else if (items && typeof items === 'object') {
            let possibleArray = Object.values(items).find(val => Array.isArray(val));
            if (!possibleArray && items.data && typeof items.data === 'object') {
                possibleArray = Object.values(items.data).find(val => Array.isArray(val));
            }
            list = possibleArray ? possibleArray : [items];
        }

        // Filter out pure metadata objects (no part identity at all)
        list = list.filter(item =>
            item.articleId || item.articleNo || item.brandName || item.mfrName ||
            item.supplierName || item.articleProductName || item.name ||
            item.vehicleId || item.carId || item.manuId
        );

        if (!list || list.length === 0) {
            resultsContainer.innerHTML = `
                <div class="status-message">
                    No matching results found in the catalog.
                    <br><br><small style="color:var(--text-muted);">API returned 0 valid items.</small>
                </div>
            `;
            return;
        }

        // Store full list and reset pagination
        _allResults = list;
        _currentPage = 0;
        resultsContainer.innerHTML = '';
        renderPage(0);
    }
});
