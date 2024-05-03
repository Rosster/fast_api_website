await pyodide.loadPackage('micropip');
const micropip = pyodide.pyimport('micropip');
await micropip.install(['pandas', 'requests', 'great-tables']);

await fetch("/cme_summary").then(o=> o.json()).then(o => window.cme_summary_data = o)
await fetch("/cme_data").then(o=> o.json()).then(o => window.cme_data = o)
