function getApiKey() {
  return document.getElementById("apiKey").value.trim();
}

function getKatanoxToken() {
  return document.getElementById("katanoxToken").value.trim();
}

function ensureKatanoxToken() {
  if (!getKatanoxToken()) {
    throw new Error("Katanox API token is required.");
  }
}

function parseCsvIds(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function setResult(id, value, isError = false) {
  const el = document.getElementById(id);
  el.classList.toggle("error", isError);
  el.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function buildHeaders() {
  const headers = {};
  const apiKey = getApiKey();
  const token = getKatanoxToken();

  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  if (token) {
    headers["X-Katanox-Token"] = token;
  }
  return headers;
}

async function localApi(path, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  const authHeaders = buildHeaders();
  Object.assign(headers, authHeaders);

  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? payload.detail
        : JSON.stringify(payload);
    throw new Error(`${response.status}: ${detail}`);
  }
  return payload;
}

function toIsoDateString(date) {
  return date.toISOString().slice(0, 10);
}

function addDays(date, days) {
  const clone = new Date(date.getTime());
  clone.setDate(clone.getDate() + days);
  return clone;
}

async function onFetchProperties() {
  ensureKatanoxToken();
  const ids = parseCsvIds(document.getElementById("propertyIds").value);
  const params = new URLSearchParams();
  ids.forEach((id) => params.append("property_ids", id));

  const query = params.toString();
  const path = query ? `/api/katanox/properties?${query}` : "/api/katanox/properties";
  const payload = await localApi(path);
  setResult("propertiesResult", payload);
}

async function onSearchAvailability() {
  ensureKatanoxToken();

  const checkIn = document.getElementById("checkIn").value;
  const checkOut = document.getElementById("checkOut").value;
  if (!checkIn || !checkOut) {
    throw new Error("Check-in and check-out are required.");
  }

  const propertyIds = parseCsvIds(document.getElementById("availabilityPropertyIds").value);
  const latValue = document.getElementById("lat").value.trim();
  const lngValue = document.getElementById("lng").value.trim();

  if (!propertyIds.length && (!latValue || !lngValue)) {
    throw new Error("Provide property IDs or both latitude and longitude.");
  }

  const params = new URLSearchParams();
  params.set("check_in", checkIn);
  params.set("check_out", checkOut);
  params.set("adults", document.getElementById("adults").value || "1");
  params.set("children", document.getElementById("children").value || "0");
  params.set("number_of_units", document.getElementById("numberOfUnits").value || "1");
  params.set("lowest", String(document.getElementById("lowest").checked));
  params.set("price_breakdown", String(document.getElementById("priceBreakdown").checked));
  params.set(
    "separate_rates_per_payment",
    String(document.getElementById("separateRatesPerPayment").checked),
  );

  if (propertyIds.length) {
    propertyIds.forEach((id) => params.append("property_ids", id));
  } else {
    params.set("lat", latValue);
    params.set("lng", lngValue);
    params.set("radius", document.getElementById("radius").value || "2000");
    params.set("page", document.getElementById("page").value || "0");
    params.set("limit", document.getElementById("limit").value || "10");
  }

  const corporateProfileId = document.getElementById("corporateProfileId").value.trim();
  if (corporateProfileId) {
    params.set("corporate_profile_id", corporateProfileId);
  }

  const unitType = document.getElementById("unitType").value.trim();
  if (unitType) {
    params.set("unit_type", unitType);
  }

  const occupancy = document.getElementById("occupancy").value.trim();
  if (occupancy) {
    params.set("occupancy", occupancy);
  }

  const payload = await localApi(`/api/katanox/availability?${params.toString()}`);
  setResult("availabilityResult", payload);
}

async function onFetchBooking() {
  ensureKatanoxToken();

  const bookingId = document.getElementById("bookingId").value.trim();
  if (!bookingId) {
    throw new Error("Booking ID is required.");
  }

  const payload = await localApi(`/api/katanox/bookings/${encodeURIComponent(bookingId)}`);
  setResult("bookingResult", payload);
}

async function onCreateBooking() {
  ensureKatanoxToken();

  const raw = document.getElementById("bookingPayload").value.trim();
  if (!raw) {
    throw new Error("Booking payload JSON is required.");
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw new Error(`Invalid JSON: ${error.message}`);
  }

  const result = await localApi("/api/katanox/bookings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setResult("createBookingResult", result);
}

async function runAction(action, outputId) {
  setResult(outputId, "Loading...");
  try {
    await action();
  } catch (error) {
    setResult(outputId, error.message || "Unexpected error", true);
  }
}

function initializeDefaults() {
  const today = new Date();
  document.getElementById("checkIn").value = toIsoDateString(addDays(today, 7));
  document.getElementById("checkOut").value = toIsoDateString(addDays(today, 9));

  const samplePayload = {
    customer: {
      address_line_1: "123 Main Street",
      city: "New York",
      country: "US",
      email: "guest@example.com",
      first_name: "John",
      last_name: "Doe",
      phone_number: "+12125551212",
      postcode: "10001",
    },
    payment: {
      type: "VISA",
      card_holder: "John Doe",
      card_number: "4111111111111111",
      expiry_month: "12",
      expiry_year: "2030",
      cvv: "123",
    },
    reservations: [
      {
        offer_id: "replace-with-offer-id",
      },
    ],
  };

  document.getElementById("bookingPayload").value = JSON.stringify(samplePayload, null, 2);
}

async function onTestConnection() {
  const payload = await localApi("/api/health");
  setResult("connectionResult", payload);
}

function bindClick(id, handler) {
  const el = document.getElementById(id);
  if (!el) {
    return;
  }
  el.addEventListener("click", handler);
}

function initialize() {
  initializeDefaults();
  setResult(
    "connectionResult",
    "Press 'Test Local API Connection'. If it fails, ensure the backend is running on port 8000.",
  );

  bindClick("testConnectionBtn", () => runAction(onTestConnection, "connectionResult"));
  bindClick("fetchPropertiesBtn", () => runAction(onFetchProperties, "propertiesResult"));
  bindClick("searchAvailabilityBtn", () => runAction(onSearchAvailability, "availabilityResult"));
  bindClick("fetchBookingBtn", () => runAction(onFetchBooking, "bookingResult"));
  bindClick("createBookingBtn", () => runAction(onCreateBooking, "createBookingResult"));
}

initialize();
