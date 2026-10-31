(() => {
  const input = document.getElementById('search');
  const results = document.getElementById('search-results');
  const index = JSON.parse(document.getElementById('search-index').textContent);
  input.addEventListener('input', () => {
    const query = input.value.trim().toLocaleLowerCase();
    results.replaceChildren();
    results.hidden = !query;
    if (!query) return;
    for (const item of index.filter(row => `${row.title} ${row.name} ${row.brief}`.toLocaleLowerCase().includes(query)).slice(0, 25)) {
      const link = document.createElement('a');
      link.href = `${item.group}.html#${item.id}`;
      link.append(document.createTextNode(item.title));
      const name = document.createElement('small');
      name.textContent = item.name;
      link.append(name);
      results.append(link);
    }
  });
  const menu = document.querySelector('.menu-toggle');
  const setNavigation = open => {
    menu.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('navigation-open', open);
  };
  menu.addEventListener('click', () => setNavigation(menu.getAttribute('aria-expanded') !== 'true'));
  document.getElementById('project-navigation').addEventListener('click', event => {
    if (event.target.closest('a')) setNavigation(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') setNavigation(false);
  });
  const links = new Map([...document.querySelectorAll('.page-toc a')].map(link => [link.hash.slice(1), link]));
  let active;
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      active?.classList.remove('active');
      active?.removeAttribute('aria-current');
      active = links.get(entry.target.id);
      active.classList.add('active');
      active.setAttribute('aria-current', 'location');
    }
  }, {rootMargin: '-15% 0px -65% 0px'});
  for (const id of links.keys()) observer.observe(document.getElementById(id));
})();
