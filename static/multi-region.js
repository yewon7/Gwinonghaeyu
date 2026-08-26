function enableMultiRegion() {
    const sigun = document.querySelector('#sigun');
    if (!sigun) return;

    sigun.multiple = true;
    const selected = new Set();
    const wrapper = document.createElement('span');
    wrapper.className = 'multi';
    wrapper.id = 'sigunSelect';
    wrapper.innerHTML = '<button type="button" id="sigunButton">지역을 골라유 <i>⌄</i></button><div class="crop-menu" id="sigunMenu"><div class="crop-tools"><input id="sigunSearch" placeholder="시·군 이름 검색"><button type="button" id="clearSiguns">초기화</button></div><div id="sigunOptions"></div></div>';
    sigun.hidden = true;
    sigun.parentElement.append(wrapper);

    const button = wrapper.querySelector('#sigunButton');
    const options = wrapper.querySelector('#sigunOptions');
    const search = wrapper.querySelector('#sigunSearch');

    function updateButton() {
        const names = [...selected];
        button.innerHTML = `${names.length ? names.slice(0, 2).join(', ') + (names.length > 2 ? ` 외 ${names.length - 2}개` : '') : '지역을 골라유'} <i>⌄</i>`;
    }

    function render(filter = '') {
        options.innerHTML = [...sigun.options]
            .filter(option => option.value && option.textContent.includes(filter))
            .map(option => `<label class="crop-option"><input type="checkbox" value="${option.value}" ${selected.has(option.value) ? 'checked' : ''}> ${option.textContent}</label>`)
            .join('');
        options.querySelectorAll('input').forEach(input => {
            input.onchange = () => {
                input.checked ? selected.add(input.value) : selected.delete(input.value);
                [...sigun.options].forEach(option => { option.selected = selected.has(option.value); });
                updateButton();
            };
        });
    }

    button.onclick = () => wrapper.classList.toggle('open');
    document.addEventListener('click', event => {
        if (!wrapper.contains(event.target)) wrapper.classList.remove('open');
    });
    search.oninput = event => render(event.target.value);
    wrapper.querySelector('#clearSiguns').onclick = () => {
        selected.clear();
        [...sigun.options].forEach(option => { option.selected = false; });
        render(search.value);
        updateButton();
    };

    const observer = new MutationObserver(() => render(search.value));
    observer.observe(sigun, {childList: true});
    render();
    updateButton();

    const originalFetch = window.fetch;
    window.fetch = (input, init) => {
        if (init && typeof init.body === 'string' && String(input).endsWith('/api/recommend')) {
            const body = JSON.parse(init.body);
            body.sigun = [...selected];
            init = {...init, body: JSON.stringify(body)};
        }
        return originalFetch(input, init);
    };
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enableMultiRegion, {once: true});
} else {
    enableMultiRegion();
}
