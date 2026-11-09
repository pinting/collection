const CSV_FILE = "albums.csv";
const ALL = "";

const shelf = document.getElementById("shelf");
const genresNav = document.getElementById("genres");
const toggleGenres = document.getElementById("toggle-genres");

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

function toAlbum(record) {
  return {
    ...record,
    rank: Number(record.rank),
    genres: record.genres ? record.genres.split("|") : [],
  };
}

function iconLink(url, platform, label) {
  const element = document.createElement(url ? "a" : "span");

  element.className = url ? platform : "missing";
  element.title = url ? `Open on ${label}` : `Not on ${label}`;
  element.setAttribute("aria-label", element.title);
  element.innerHTML = `<svg aria-hidden="true"><use href="#icon-${platform}"></use></svg>`;

  if (url) {
    element.href = url;
    element.target = "_blank";
    element.rel = "noopener noreferrer";
  }

  return element;
}

function albumCard(album) {
  const card = document.createElement("article");
  const info = document.createElement("div");
  const title = document.createElement("strong");
  const artists = document.createElement("span");
  const year = document.createElement("span");
  const sleeve = document.createElement("figure");
  const cover = document.createElement("img");
  const links = document.createElement("div");

  card.className = "album";
  info.className = "info";
  info.title = `${album.artists} – ${album.album}`;
  sleeve.className = "sleeve";
  cover.src = album.cover;
  cover.alt = `${album.artists} – ${album.album}`;
  cover.loading = "lazy";
  title.textContent = album.album;
  artists.textContent = album.artists;
  year.textContent = album.year;
  links.className = "links";

  info.append(title, artists, year);
  sleeve.append(cover);
  links.append(iconLink(album.spotify_url, "spotify", "Spotify"), iconLink(album.tidal_url, "tidal", "Tidal"));
  card.append(sleeve, info, links);

  return card;
}

function countGenres(albums) {
  const counts = new Map();

  for (const album of albums) {
    for (const genre of album.genres) {
      counts.set(genre, (counts.get(genre) ?? 0) + 1);
    }
  }

  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function render(albums, selected) {
  const visible = selected === ALL ? albums : albums.filter((album) => album.genres.includes(selected));

  shelf.replaceChildren(...visible.map(albumCard));

  for (const button of genresNav.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.genre === selected));
  }
}

function renderGenres(albums, onSelect) {
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
    button(ALL, "All", albums.length),
    ...countGenres(albums).map(([genre, count]) => button(genre, genre, count)),
  );
}

function setGenresExpanded(expanded, total) {
  genresNav.classList.toggle("collapsed", !expanded);
  toggleGenres.setAttribute("aria-expanded", String(expanded));
  toggleGenres.textContent = expanded ? "Fewer genres" : `All ${total} genres`;
}

function initGenresToggle(total, selected) {
  const hidden = () => genresNav.scrollHeight > genresNav.clientHeight;
  const active = genresNav.querySelector('[aria-pressed="true"]');

  setGenresExpanded(false, total);
  toggleGenres.hidden = !hidden();
  setGenresExpanded(selected !== ALL && active?.offsetTop >= genresNav.clientHeight, total);
  toggleGenres.addEventListener("click", () => {
    setGenresExpanded(genresNav.classList.contains("collapsed"), total);
  });
}

async function main() {
  const response = await fetch(CSV_FILE, { cache: "no-cache" });

  if (!response.ok) {
    throw new Error(`${CSV_FILE}: HTTP ${response.status}`);
  }

  const albums = parseCsv(await response.text()).map(toAlbum).sort((a, b) => a.rank - b.rank);
  const select = (genre) => {
    history.replaceState(null, "", genre === ALL ? location.pathname : `#${encodeURIComponent(genre)}`);
    render(albums, genre);
  };

  renderGenres(albums, select);

  const selected = decodeURIComponent(location.hash.slice(1));

  render(albums, selected);
  initGenresToggle(genresNav.childElementCount - 1, selected);
}

main().catch((error) => {
  const notice = document.createElement("p");

  notice.className = "notice";
  notice.textContent = `Could not load the albums (${error.message}). Serve this folder with: python -m http.server --directory docs 8000`;
  shelf.replaceChildren(notice);
});
