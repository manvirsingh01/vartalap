const state = {
  username: null,
  roomCode: null,
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
    document.getElementById("room-title").textContent = `Room ${data.code}`
    document.getElementById("messages").innerHTML = ""
    setStatus(joinRoomStatus, data.message)
    showChat(true)
    await loadMessages(true)
  } catch (error) {
    setStatus(joinRoomStatus, error.message, true)
  }
}

async function leaveRoom() {
  try {
    const data = await apiRequest("/api/rooms/leave", { method: "POST" })
    state.roomCode = null
    state.lastMessageId = 0
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
    await apiRequest(`/api/rooms/${state.roomCode}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
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
    renderMessages(messages)
  } catch (error) {
    setStatus(chatStatus, error.message, true)
  }
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
