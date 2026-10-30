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
})();
