/* انتخاب‌گرِ صنف — جست‌وجو + فیلترِ رسته + انتخابِ کارت (بخشِ ۴).
   خالص/بدونِ وابستگی؛ فقط با کلاس/attribute کار می‌کند تا در هر سه محیط
   (صفحه‌ی عمومی، ویزاردِ ساختِ فروشگاه، تنظیماتِ مرچنت) یکسان کار کند. */

function industryNormalizePersian(text) {
  return (text || "")
    .toLowerCase()
    .replace(/ي/g, "ی") // ي -> ی
    .replace(/ك/g, "ک") // ك -> ک
    .replace(/[ً-ْ]/g, "") // اعراب
    .replace(/\s+/g, " ")
    .trim();
}

function industryFilterSearch(query) {
  var q = industryNormalizePersian(query);
  var cards = document.querySelectorAll(".industry-card");
  var visible = 0;
  cards.forEach(function (card) {
    var name = industryNormalizePersian(card.getAttribute("data-name"));
    var sectorLabel = industryNormalizePersian(card.getAttribute("data-sector-label"));
    var matches = q === "" || name.indexOf(q) !== -1 || sectorLabel.indexOf(q) !== -1;
    var activeTab = document.querySelector(".industry-tab.active");
    var sectorOk = !activeTab || activeTab.getAttribute("data-sector") === "all"
      || card.getAttribute("data-sector") === activeTab.getAttribute("data-sector");
    var show = matches && sectorOk;
    card.style.display = show ? "" : "none";
    if (show) visible++;
  });
  var empty = document.getElementById("industryEmpty");
  if (empty) empty.style.display = visible === 0 ? "block" : "none";
}

function industryFilterSector(sector, searchInputId) {
  document.querySelectorAll(".industry-tab").forEach(function (t) {
    t.classList.toggle("active", t.getAttribute("data-sector") === sector);
  });
  var input = searchInputId ? document.getElementById(searchInputId) : document.querySelector(".industry-search input");
  industryFilterSearch(input ? input.value : "");
}

function industrySelectCard(card, hiddenInputId) {
  document.querySelectorAll(".industry-card").forEach(function (c) { c.classList.remove("selected"); });
  card.classList.add("selected");
  var hidden = hiddenInputId ? document.getElementById(hiddenInputId) : null;
  if (hidden) hidden.value = card.getAttribute("data-id");
  var displayName = document.getElementById("industrySelectedName");
  if (displayName) displayName.textContent = card.getAttribute("data-name");
  var continueBtn = document.getElementById("industryContinueBtn");
  if (continueBtn) continueBtn.disabled = false;
}
