const ALL = "";

const shelf = document.getElementById("shelf");
const genresNav = document.getElementById("genres");
const toggleGenres = document.getElementById("toggle-genres");
const viewTabs = document.querySelectorAll(".view-link");

const COLLECTIONS = {
  music: {
    csv: "albums.csv",
    title: "slash music slash favorites",
    hasGenres: true,
    toItem: (r) => ({
      type: "music",
      rank: Number(r.rank),
      title: r.album,
      creator: r.artists,
      year: r.year,
      cover: r.cover,
      link1: { url: r.spotify_url, platform: "spotify", label: "Spotify" },
      link2: { url: r.tidal_url, platform: "tidal", label: "Tidal" },
      genres: r.genres ? r.genres.split("|") : [],
    }),
  },
  movies: {
    csv: "movies.csv",
    title: "slash films slash favorites",
    hasGenres: false,
    toItem: (r) => ({
      type: "movies",
      rank: Number(r.rank),
      title: r.title,
      creator: r.director,
      year: r.year,
      cover: r.cover,
      link1: { url: r.imdb_url, platform: "imdb", label: "IMDb" },
      link2: { url: r.letterboxd_url, platform: "letterboxd", label: "Letterboxd" },
      genres: [],
    }),
  },
};

const dataCache = new Map();

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      rows.push([...row, field.replace(/\r$/, "")]);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }

  if (field || row.length) {
    rows.push([...row, field]);
  }

  const [header, ...records] = rows;
  return records.map((record) => Object.fromEntries(header.map((name, i) => [name, record[i] ?? ""])));
}

async function loadCollection(viewName) {
  if (dataCache.has(viewName)) {
    return dataCache.get(viewName);
  }

  const config = COLLECTIONS[viewName];
  if (!config) throw new Error(`Unknown view: ${viewName}`);

  const response = await fetch(config.csv, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`${config.csv}: HTTP ${response.status}`);
  }

  const items = parseCsv(await response.text()).map(config.toItem).sort((a, b) => a.rank - b.rank);
  dataCache.set(viewName, items);
  return items;
}

function textLink(link) {
  const element = document.createElement(link.url ? "a" : "span");

  element.className = `link-item ${link.platform}${link.url ? "" : " missing"}`;
  element.textContent = link.platform.toLowerCase();
  element.title = link.url ? `Open on ${link.label}` : `Not on ${link.label}`;

  if (link.url) {
    element.href = link.url;
    element.target = "_blank";
    element.rel = "noopener noreferrer";
  }

  return element;
}

function itemCard(item) {
  const card = document.createElement("article");
  const info = document.createElement("div");
  const title = document.createElement("strong");
  const creator = document.createElement("span");
  const year = document.createElement("span");
  const sleeve = document.createElement("figure");
  const cover = document.createElement("img");
  const links = document.createElement("div");
  const sep = document.createElement("span");

  card.className = `item-card ${item.type === "movies" ? "movie" : "album"}`;
  info.className = "info";
  info.title = `${item.creator} – ${item.title}`;
  sleeve.className = `sleeve ${item.type === "movies" ? "poster" : ""}`;
  cover.src = item.cover;
  cover.alt = `${item.creator} – ${item.title}`;
  cover.loading = "lazy";
  title.textContent = item.title;
  creator.textContent = item.creator;
  year.textContent = item.year;
  links.className = "links";

  sep.className = "link-sep";
  sep.textContent = "·";
  sep.setAttribute("aria-hidden", "true");

  info.append(title, creator, year);
  sleeve.append(cover);
  links.append(textLink(item.link1), sep, textLink(item.link2));
  card.append(sleeve, info, links);

  return card;
}

function countGenres(items) {
  const counts = new Map();

  for (const item of items) {
    for (const genre of item.genres) {
      counts.set(genre, (counts.get(genre) ?? 0) + 1);
    }
  }

  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function renderShelf(items, selectedGenre) {
  const visible = selectedGenre === ALL ? items : items.filter((item) => item.genres.includes(selectedGenre));
  shelf.replaceChildren(...visible.map(itemCard));

  for (const button of genresNav.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.genre === selectedGenre));
  }
}

function renderGenres(items, onSelect) {
  const button = (genre, label, count) => {
    const element = document.createElement("button");
    const amount = document.createElement("span");

    element.type = "button";
    element.dataset.genre = genre;
    amount.textContent = ` ${count}`;
    element.append(label, amount);
    element.addEventListener("click", () => onSelect(genre));

    return element;
  };

  genresNav.replaceChildren(
    button(ALL, "All", items.length),
    ...countGenres(items).map(([genre, count]) => button(genre, genre, count)),
  );
}

function setGenresExpanded(expanded, total) {
  genresNav.classList.toggle("collapsed", !expanded);
  toggleGenres.setAttribute("aria-expanded", String(expanded));
  toggleGenres.textContent = expanded ? "Fewer genres" : `All ${total} genres`;
}

function initGenresToggle(total, selectedGenre) {
  const hidden = () => genresNav.scrollHeight > genresNav.clientHeight;
  const active = genresNav.querySelector('[aria-pressed="true"]');

  setGenresExpanded(false, total);
  toggleGenres.hidden = !hidden();
  setGenresExpanded(selectedGenre !== ALL && active?.offsetTop >= genresNav.clientHeight, total);
  toggleGenres.onclick = () => {
    setGenresExpanded(genresNav.classList.contains("collapsed"), total);
  };
}

function parseRoute() {
  const hash = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  const defaultView = window.DEFAULT_VIEW || "music";

  if (!hash) {
    return { view: defaultView, genre: ALL };
  }

  // Format: "music/Rock" or "movies/Drama" or "films" or "music" or "movies"
  const [first, ...rest] = hash.split("/");
  if (first === "music") {
    return { view: "music", genre: rest.join("/") || ALL };
  }
  if (first === "movies" || first === "films") {
    return { view: "movies", genre: rest.join("/") || ALL };
  }

  // Backward compatibility with legacy `#Genre`
  return { view: defaultView, genre: hash };
}

function updateNav(view) {
  document.title = COLLECTIONS[view]?.title || "slash favorites";
  for (const tab of viewTabs) {
    tab.classList.toggle("active", tab.dataset.view === view);
  }
}

async function show(view, genre) {
  updateNav(view);
  const items = await loadCollection(view);
  const config = COLLECTIONS[view] || {};

  document.body.classList.toggle("has-genres", Boolean(config.hasGenres));

  if (!config.hasGenres) {
    genresNav.classList.add("collapsed");
    genresNav.replaceChildren();
    genresNav.style.display = "none";
    toggleGenres.hidden = true;
    renderShelf(items, ALL);
    return;
  }

  genresNav.style.display = "";
  const selectGenre = (newGenre) => {
    const routePrefix = view === "movies" ? "films" : view;
    const newHash = newGenre === ALL ? `#/${routePrefix}` : `#/${routePrefix}/${encodeURIComponent(newGenre)}`;
    history.replaceState(null, "", newHash);
    renderShelf(items, newGenre);
  };

  renderGenres(items, selectGenre);
  renderShelf(items, genre);
  initGenresToggle(genresNav.childElementCount - 1, genre);
}

async function main() {
  let { view, genre } = parseRoute();
  await show(view, genre);

  window.addEventListener("hashchange", async () => {
    const route = parseRoute();
    await show(route.view, route.genre);
  });

  for (const tab of viewTabs) {
    tab.addEventListener("click", async (e) => {
      const targetView = tab.dataset.view;
      if (!targetView) return;
      e.preventDefault();
      const routePrefix = targetView === "movies" ? "films" : targetView;
      history.replaceState(null, "", `#/${routePrefix}`);
      await show(targetView, ALL);
    });
  }
}

main().catch((error) => {
  const notice = document.createElement("p");
  notice.className = "notice";
  notice.textContent = `Could not load favorites (${error.message}). Serve this folder with: python -m http.server --directory docs 8000`;
  shelf.replaceChildren(notice);
});
