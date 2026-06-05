const state = {
  username: null,
  roomCode: null,
  roomKey: null,
  lastMessageId: 0,
  pollTimer: null,
}

const profileStatus = document.getElementById("profile-status")
const createRoomStatus = document.getElementById("create-room-status")
const joinRoomStatus = document.getElementById("join-room-status")
const chatStatus = document.getElementById("chat-status")

function setStatus(element, message, isError = false) {
  element.textContent = message
  element.classList.toggle("error", isError)
}

async function apiRequest(url, options = {}) {
  const headers = options.headers || {}
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json"
  }
  const response = await fetch(url, { ...options, headers })
  let data = null
  try {
    data = await response.json()
  } catch (error) {
    throw new Error("Invalid server response.")
  }
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "Request failed.")
  }
  return data
}

function showSections() {
  document.getElementById("rooms-section").classList.remove("hidden")
  document.getElementById("create-room-section").classList.remove("hidden")
  document.getElementById("join-room-section").classList.remove("hidden")
}

function showChat(show) {
  const chatSection = document.getElementById("chat-section")
  chatSection.classList.toggle("hidden", !show)
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ""
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte)
  })
  return btoa(binary)
}

function fromBase64(base64) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

async function deriveRoomKey(roomCode, password) {
  if (!window.crypto || !window.crypto.subtle) {
    throw new Error("Web Crypto not available. Use HTTPS or localhost.")
  }
  const encoder = new TextEncoder()
  const base = password || roomCode
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    encoder.encode(base),
    "PBKDF2",
    false,
    ["deriveKey"],
  )
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: encoder.encode(`vartalap:${roomCode}`),
      iterations: 100000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  )
}

async function encryptText(text) {
  if (!state.roomKey) {
    throw new Error("Room key not ready.")
  }
  const encoder = new TextEncoder()
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    state.roomKey,
    encoder.encode(text),
  )
  return { ciphertext: toBase64(ciphertext), iv: toBase64(iv) }
}

async function decryptText(ciphertext, iv) {
  if (!state.roomKey) {
    return null
  }
  try {
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: fromBase64(iv) },
      state.roomKey,
      fromBase64(ciphertext),
    )
    return new TextDecoder().decode(plaintext)
  } catch (error) {
    if (error && error.name === "OperationError") {
      return null
    }
    throw error
  }
}

async function createProfile(create) {
  const username = document.getElementById("username").value.trim()
  const password = document.getElementById("password").value
  if (!username || !password) {
    setStatus(profileStatus, "Username and password are required.", true)
    return
  }
  try {
    const data = await apiRequest("/api/profile", {
      method: "POST",
      body: JSON.stringify({ username, password, create }),
    })
    state.username = username
    setStatus(profileStatus, data.message)
    showSections()
    await refreshRooms()
  } catch (error) {
    setStatus(profileStatus, error.message, true)
  }
}

async function refreshRooms() {
  try {
    const data = await apiRequest("/api/rooms")
    renderRooms(data.rooms || [])
  } catch (error) {
    setStatus(joinRoomStatus, error.message, true)
  }
}

function renderRooms(rooms) {
  const list = document.getElementById("rooms-list")
  list.innerHTML = ""
  if (!rooms.length) {
    list.textContent = "No rooms available."
    return
  }
  rooms.forEach((room) => {
    const item = document.createElement("div")
    item.className = "list-item"
    const text = document.createElement("div")
    const lock = room.requires_password ? "Password" : "Open"
    text.textContent = `${room.code} | ${room.name} | Active: ${room.active_count} | ${lock}`
    const joinButton = document.createElement("button")
    joinButton.textContent = "Join"
    joinButton.addEventListener("click", () => {
      document.getElementById("join-room-code").value = room.code
      joinRoom()
    })
    item.appendChild(text)
    item.appendChild(joinButton)
    list.appendChild(item)
  })
}

async function createRoom() {
  const name = document.getElementById("room-name").value.trim()
  const password = document.getElementById("room-password").value
  if (!name) {
    setStatus(createRoomStatus, "Room name is required.", true)
    return
  }
  try {
    const data = await apiRequest("/api/rooms", {
      method: "POST",
      body: JSON.stringify({ name, password }),
    })
    setStatus(createRoomStatus, `${data.message} Code: ${data.code}`)
    await refreshRooms()
  } catch (error) {
    setStatus(createRoomStatus, error.message, true)
  }
}

async function joinRoom() {
  const code = document.getElementById("join-room-code").value.trim().toUpperCase()
  const password = document.getElementById("join-room-password").value
  if (!code) {
    setStatus(joinRoomStatus, "Room code is required.", true)
    return
  }
  try {
    const data = await apiRequest("/api/rooms/join", {
      method: "POST",
      body: JSON.stringify({ code, password }),
    })
    state.roomCode = data.code
    state.lastMessageId = 0
    state.roomKey = await deriveRoomKey(data.code, password)
    document.getElementById("room-title").textContent = `Room ${data.code}`
    document.getElementById("messages").innerHTML = ""
    setStatus(joinRoomStatus, data.message)
    showChat(true)
    await loadMessages(true)
    await updateMembers()
  } catch (error) {
    setStatus(joinRoomStatus, error.message, true)
  }
}

async function leaveRoom() {
  try {
    const data = await apiRequest("/api/rooms/leave", { method: "POST" })
    state.roomCode = null
    state.lastMessageId = 0
    state.roomKey = null
    renderMembers([])
    setStatus(chatStatus, data.message)
    showChat(false)
  } catch (error) {
    setStatus(chatStatus, error.message, true)
  }
}

async function sendMessage() {
  const input = document.getElementById("message-input")
  const text = input.value.trim()
  if (!text) {
    return
  }
  if (!state.roomCode) {
    setStatus(chatStatus, "Join a room first.", true)
    return
  }
  try {
    const payload = await encryptText(text)
    await apiRequest(`/api/rooms/${state.roomCode}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    })
    input.value = ""
    await loadMessages(false)
  } catch (error) {
    setStatus(chatStatus, error.message, true)
  }
}

async function loadMessages(showAll) {
  if (!state.roomCode) {
    return
  }
  const since = showAll ? "" : `?since=${state.lastMessageId}`
  try {
    const data = await apiRequest(`/api/rooms/${state.roomCode}/messages${since}`)
    const messages = data.messages || []
    const decoded = await decodeMessages(messages)
    renderMessages(decoded)
  } catch (error) {
    setStatus(chatStatus, error.message, true)
  }
}

async function decodeMessages(messages) {
  const decoded = []
  for (const message of messages) {
    if (message.text) {
      decoded.push(message)
      continue
    }
    if (message.ciphertext && message.iv) {
      const text = await decryptText(message.ciphertext, message.iv)
      decoded.push({ ...message, text: text || "[Encrypted message - unable to decrypt]" })
      continue
    }
    decoded.push({ ...message, text: "[Unsupported message]" })
  }
  return decoded
}

async function updateMembers() {
  if (!state.roomCode) {
    return
  }
  try {
    const data = await apiRequest(`/api/rooms/${state.roomCode}/members`)
    renderMembers(data.members || [])
  } catch (error) {
    setStatus(chatStatus, error.message, true)
  }
}

function renderMembers(members) {
  const list = document.getElementById("members-list")
  list.innerHTML = ""
  if (!members.length) {
    list.textContent = "No members yet."
    return
  }
  members.forEach((member) => {
    const item = document.createElement("div")
    item.className = "list-item"
    const name = document.createElement("div")
    name.textContent = member.username
    const status = document.createElement("div")
    const online = member.online ? "Online" : "Offline"
    const inRoom = member.in_room ? "In room" : "Away"
    status.textContent = `${online} · ${inRoom}`
    status.className = `member-status ${member.online ? "online" : "offline"}`
    item.appendChild(name)
    item.appendChild(status)
    list.appendChild(item)
  })
}

function renderMessages(messages) {
  if (!messages.length) {
    return
  }
  const container = document.getElementById("messages")
  messages.forEach((message) => {
    state.lastMessageId = Math.max(state.lastMessageId, Number(message.id || 0))
    const item = document.createElement("div")
    item.className = "message"
    item.textContent = `[${message.ts}] ${message.sender}: ${message.text}`
    container.appendChild(item)
  })
  container.scrollTop = container.scrollHeight
}

function startPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer)
  }
  state.pollTimer = setInterval(() => {
    if (state.roomCode) {
      loadMessages(false)
      updateMembers()
    }
  }, 2000)
}

document.getElementById("create-profile").addEventListener("click", () => createProfile(true))
document.getElementById("login-profile").addEventListener("click", () => createProfile(false))
document.getElementById("refresh-rooms").addEventListener("click", refreshRooms)
document.getElementById("create-room").addEventListener("click", createRoom)
document.getElementById("join-room").addEventListener("click", joinRoom)
document.getElementById("leave-room").addEventListener("click", leaveRoom)
document.getElementById("send-message").addEventListener("click", sendMessage)
document.getElementById("message-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    sendMessage()
  }
})

startPolling()
