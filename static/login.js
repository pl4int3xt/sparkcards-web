const nameEl = document.getElementById("name");
const birthEl = document.getElementById("birthdate");
const phoneEl = document.getElementById("phone");
const walletBtn = document.getElementById("walletBtn");
const hintEl = document.getElementById("hint");
const topError = document.getElementById("topError");

const wrapName = document.getElementById("f_name");
const wrapBirth = document.getElementById("f_birthdate");
const wrapPhone = document.getElementById("f_phone");

// Phone input with country panel
const iti = window.intlTelInput(phoneEl, {
  initialCountry: "es",
  separateDialCode: true,
  preferredCountries: ["es", "fr", "de", "it", "pt", "gb", "us"],
  utilsScript: "https://cdn.jsdelivr.net/npm/intl-tel-input@19.5.6/build/js/utils.js",
});

// Stable device id (same pass per browser)
function getDeviceId() {
  let v = localStorage.getItem("sparkcards_device_id");
  if (!v) {
    v = crypto.randomUUID();
    localStorage.setItem("sparkcards_device_id", v);
  }
  return v;
}
const deviceId = getDeviceId();

let saveUrl = null;
let issuing = false;
let lastIssuedName = null;
let nameDirty = false;

function showError(msg) {
  topError.textContent = msg;
  topError.style.display = "block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function clearError() {
  topError.style.display = "none";
  topError.textContent = "";
}

function setInvalid(wrap, bad) {
  if (bad) wrap.classList.add("invalid");
  else wrap.classList.remove("invalid");
}

function getPhoneE164() {
  try {
    return iti.getNumber();
  } catch {
    return "";
  }
}

function validateForButton() {
  const nameOk = nameEl.value.trim().length > 0;
  const birthOk = birthEl.value.trim().length > 0;
  const phoneOk = phoneEl.value.trim().length > 0 && iti.isValidNumber();

  setInvalid(wrapName, !nameOk);
  setInvalid(wrapBirth, !birthOk);
  setInvalid(wrapPhone, !phoneOk);

  return nameOk && birthOk && phoneOk;
}

async function issuePass() {
  const name = nameEl.value.trim();
  if (!name || issuing || name === lastIssuedName) return;

  issuing = true;
  hintEl.textContent = "Generando pase…";

  try {
    const res = await fetch("/issue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: name,
        birthdate: birthEl.value || "",
        phone: getPhoneE164(),
        object_id: deviceId,
      }),
    });

    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Issue failed");

    saveUrl = data.save_url;
    lastIssuedName = name;

    hintEl.textContent = "Pase listo. Completa los datos y añádelo.";
    clearError();

    walletBtn.disabled = !validateForButton();
  } catch (e) {
    showError("Error creando el pase");
  } finally {
    issuing = false;
    nameDirty = false;
  }
}

// EVENTS

nameEl.addEventListener("input", () => {
  nameDirty = true;
  walletBtn.disabled = true;
  hintEl.textContent = "Escribiendo…";
});

// Key behavior: only issue when leaving the name input
nameEl.addEventListener("blur", () => {
  if (nameDirty) issuePass();
});

birthEl.addEventListener("change", () => {
  if (saveUrl) walletBtn.disabled = !validateForButton();
});

phoneEl.addEventListener("input", () => {
  if (saveUrl) walletBtn.disabled = !validateForButton();
});

walletBtn.addEventListener("click", (e) => {
  e.preventDefault();

  if (!validateForButton()) {
    showError("Faltan datos. Revisa los campos en rojo.");
    return;
  }

  if (saveUrl) window.location.href = saveUrl;
});

