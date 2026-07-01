import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Bell,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  FileText,
  Image,
  LogOut,
  Star,
  Users,
  Mic,
  Paperclip,
  Plus,
  Send,
  Smile,
  Square,
  Trash2,
  X,
} from "lucide-react";
import "./styles.css";

const API = "/api";
const EMOJI_CHOICES = ["😀", "😂", "😊", "😍", "👍", "👏", "🙏", "💡", "🔥", "🎉", "🤔", "😅", "😭", "❤️", "✅", "👀"];

async function request(path, options = {}) {
  const userId = sessionStorage.getItem("user_id");
  const response = await fetch(`${API}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(userId ? { "X-User-Id": userId } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function App() {
  const [currentUser, setCurrentUser] = useState(() => {
    const id = sessionStorage.getItem("user_id");
    const displayName = sessionStorage.getItem("display_name");
    return id && displayName ? { id: Number(id), display_name: displayName } : null;
  });
  const [identityDraft, setIdentityDraft] = useState("");
  const [users, setUsers] = useState([]);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const [accent, setAccent] = useState(() => localStorage.getItem("accent") || "graphite");
  const [collapsed, setCollapsed] = useState(false);
  const [channels, setChannels] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [todos, setTodos] = useState([]);
  const [memos, setMemos] = useState([]);
  const [habits, setHabits] = useState([]);
  const [relations, setRelations] = useState([]);
  const [memoryRecords, setMemoryRecords] = useState({ facts: [], notes: [] });
  const [memoryPredicates, setMemoryPredicates] = useState({ predicates: {}, groupOrder: [] });
  const [personas, setPersonas] = useState([]);
  const [nav, setNav] = useState("chat");
  const [stewardBrief, setStewardBrief] = useState(null);
  const [stewardMessages, setStewardMessages] = useState([]);
  const [stewardInput, setStewardInput] = useState("");
  const [stewardSending, setStewardSending] = useState(false);
  const [stewardTyping, setStewardTyping] = useState(false);
  const [tab, setTab] = useState("today");
  const [sheet, setSheet] = useState(null);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState([]);
  const [activePersonaId, setActivePersonaId] = useState(null);
  const [channelTitle, setChannelTitle] = useState("");
  const [newRoleDraft, setNewRoleDraft] = useState({ name: "", kind: "AI · 伙伴", core: "" });
  const [input, setInput] = useState("");
  const [mentionedMembers, setMentionedMembers] = useState([]);
  const [mentionPickerOpen, setMentionPickerOpen] = useState(false);
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [selectedUserIds, setSelectedUserIds] = useState([]);
  const [todoDraft, setTodoDraft] = useState({ title: "", dueAt: "", priority: "med" });
  const [sending, setSending] = useState(false);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState("");
  const messageEndRef = useRef(null);
  const stewardEndRef = useRef(null);
  const imageInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const recorderRef = useRef(null);
  const recordingChunksRef = useRef([]);

  const chatChannels = useMemo(
    () => channels.filter((channel) => channel.type !== "steward" && !channel.is_system),
    [channels],
  );
  const activeChannel = useMemo(
    () => chatChannels.find((channel) => channel.id === activeId) || chatChannels[0],
    [chatChannels, activeId],
  );
  const regularPersonas = useMemo(
    () => personas.filter((persona) => !persona.is_system),
    [personas],
  );
  const activePersona = useMemo(
    () => personas.find((persona) => persona.id === activePersonaId) || personas[0],
    [personas, activePersonaId],
  );
  const stewardChannel = useMemo(
    () => channels.find((channel) => channel.type === "steward" || channel.is_system),
    [channels],
  );
  const mentionableMembers = useMemo(
    () => (activeChannel?.members || []).filter((member) => member.memberType === "agent" && member.channelMemberId),
    [activeChannel?.id, activeChannel?.members],
  );

  useEffect(() => {
    localStorage.setItem("theme", theme);
    localStorage.setItem("accent", accent);
  }, [theme, accent]);

  useEffect(() => {
    if (currentUser) {
      loadInitial().catch(showError);
    }
  }, [currentUser?.id]);

  useEffect(() => {
    if (!activeChannel) return;
    setMentionedMembers([]);
    setMentionPickerOpen(false);
    setEmojiPickerOpen(false);
    loadMessages(activeChannel.id).catch(showError);
    const source = new EventSource(`${API}/channels/${activeChannel.id}/events`);
    source.addEventListener("typing", () => {
      setTyping(true);
      window.setTimeout(() => setTyping(false), 1400);
    });
    source.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.message) {
        setMessages((current) => upsertMessage(current, normalizeMessage(payload.message)));
        setTyping(false);
      }
    });
    source.addEventListener("proactive", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.message) {
        setMessages((current) => upsertMessage(current, normalizeMessage(payload.message)));
      }
    });
    return () => source.close();
  }, [activeChannel?.id]);

  useEffect(() => {
    if (!stewardChannel) return undefined;
    loadStewardMessages().catch(showError);
    const source = new EventSource(`${API}/channels/${stewardChannel.id}/events`);
    source.addEventListener("typing", () => {
      setStewardTyping(true);
      window.setTimeout(() => setStewardTyping(false), 1400);
    });
    source.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.message) {
        setStewardMessages((current) => upsertMessage(current, normalizeMessage(payload.message)));
        setStewardTyping(false);
      }
    });
    source.addEventListener("proactive", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.message) {
        setStewardMessages((current) => upsertMessage(current, normalizeMessage(payload.message)));
      }
    });
    return () => source.close();
  }, [stewardChannel?.id]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, typing]);

  useEffect(() => {
    stewardEndRef.current?.scrollIntoView({ block: "end" });
  }, [stewardMessages, stewardTyping, sheet]);

  function showError(err) {
    setError(err.message || String(err));
  }

  async function loadInitial() {
    const [
      nextChannels,
      nextTodos,
      nextMemos,
      nextHabits,
      nextRelations,
      nextMemoryRecords,
      nextMemoryPredicates,
      nextPersonas,
      brief,
      nextUsers,
    ] =
      await Promise.all([
        request("/channels"),
        request("/todos"),
        request("/memos"),
        request("/habits"),
        request("/relations").catch(() => request("/persona-state")),
        request("/memory").catch(() => ({ facts: [], notes: [] })),
        request("/memory/predicates").catch(() => ({ predicates: {}, group_order: [] })),
        request("/personas?include_system=true"),
        request("/steward/brief").catch(() => null),
        request("/users").catch(() => []),
    ]);
    const normalizedChannels = nextChannels.map(normalizeChannel);
    const firstChatChannel = normalizedChannels.find(
      (channel) => channel.type !== "steward" && !channel.is_system,
    );
    setChannels(normalizedChannels);
    setActiveId((current) => current || firstChatChannel?.id || null);
    setTodos(nextTodos.map(normalizeTodo));
    setMemos(nextMemos.map(normalizeMemo));
    setHabits(nextHabits.map(normalizeHabit));
    setRelations(nextRelations.map(normalizeRelation));
    setMemoryRecords(normalizeMemoryRecords(nextMemoryRecords));
    setMemoryPredicates(normalizeMemoryPredicates(nextMemoryPredicates));
    const normalizedPersonas = nextPersonas.map(normalizePersona);
    setPersonas(normalizedPersonas);
    setActivePersonaId((current) => current || normalizedPersonas[0]?.id || null);
    setStewardBrief(brief);
    setUsers(nextUsers);
  }

  async function chooseIdentity(event) {
    event.preventDefault();
    const displayName = identityDraft.trim();
    if (!displayName) return;
    const user = await request("/users", {
      method: "POST",
      body: JSON.stringify({ display_name: displayName }),
      headers: {},
    });
    sessionStorage.setItem("user_id", String(user.id));
    sessionStorage.setItem("display_name", user.display_name);
    setCurrentUser(user);
    setIdentityDraft("");
  }

  function handleLogout() {
    sessionStorage.removeItem("user_id");
    sessionStorage.removeItem("display_name");
    setCurrentUser(null);
    setIdentityDraft("");
    setMessages([]);
    setStewardMessages([]);
    setMentionedMembers([]);
    setSelectedUserIds([]);
    setInput("");
    setStewardInput("");
    setError("");
    setSheet(null);
  }

  async function loadMessages(channelId) {
    const payload = await request(`/channels/${channelId}/messages`);
    const rows = Array.isArray(payload) ? payload : payload.messages || [];
    setMessages(rows.map(normalizeMessage));
  }

  async function loadStewardMessages() {
    if (!stewardChannel) return;
    const payload = await request(`/channels/${stewardChannel.id}/messages`);
    const rows = Array.isArray(payload) ? payload : payload.messages || [];
    setStewardMessages(rows.map(normalizeMessage));
  }

  async function sendMessage(text = input) {
    const content = text.trim();
    if (!content || !activeChannel || sending) return;
    const mentionedIds = mentionedMembers.map((member) => member.channelMemberId);
    const optimistic = {
      id: `local-${Date.now()}`,
      senderId: "self",
      senderName: "你",
      fromSelf: true,
      text: content,
      at: new Date().toISOString(),
      status: "发送中",
      optimistic: true,
    };
    setInput("");
    setMentionedMembers([]);
    setMentionPickerOpen(false);
    setSending(true);
    setError("");
    setMessages((current) => [...current, optimistic]);
    try {
      await request(`/channels/${activeChannel.id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content,
          text: content,
          type: "text",
          mentions: [],
          mentioned_member_ids: mentionedIds,
        }),
      });
      await Promise.all([loadMessages(activeChannel.id), refreshLedger()]);
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      showError(err);
    } finally {
      setSending(false);
    }
  }

  async function uploadAttachment(file) {
    if (!activeChannel || !file) return null;
    const userId = sessionStorage.getItem("user_id");
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${API}/channels/${activeChannel.id}/attachments`, {
      method: "POST",
      headers: userId ? { "X-User-Id": userId } : {},
      body: form,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    return response.json();
  }

  async function sendAttachment(file, forcedType = null) {
    if (!file || !activeChannel || sending) return;
    const caption = input.trim();
    const mentionedIds = mentionedMembers.map((member) => member.channelMemberId);
    const previewUrl = URL.createObjectURL(file);
    const messageType = forcedType || messageTypeForFile(file);
    const optimistic = {
      id: `local-${messageType}-${Date.now()}`,
      senderId: "self",
      senderName: "你",
      fromSelf: true,
      type: messageType,
      text: caption,
      mediaUrl: previewUrl,
      mimeType: file.type,
      fileName: file.name,
      at: new Date().toISOString(),
      status: "发送中",
      optimistic: true,
    };
    setInput("");
    setMentionedMembers([]);
    setMentionPickerOpen(false);
    setSending(true);
    setError("");
    setMessages((current) => [...current, optimistic]);
    try {
      const attachment = await uploadAttachment(file);
      await request(`/channels/${activeChannel.id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content: caption,
          text: caption,
          type: messageType,
          mentions: [],
          mentioned_member_ids: mentionedIds,
          media_url: attachment.media_url,
          mime_type: attachment.mime_type,
          file_name: attachment.file_name,
        }),
      });
      await Promise.all([loadMessages(activeChannel.id), refreshLedger()]);
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      showError(err);
    } finally {
      URL.revokeObjectURL(previewUrl);
      setSending(false);
      if (imageInputRef.current) imageInputRef.current.value = "";
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function sendImage(file) {
    await sendAttachment(file, "image");
  }

  async function sendFile(file) {
    await sendAttachment(file);
  }

  function insertEmoji(emoji) {
    handleComposerChange(`${input}${emoji}`);
    setEmojiPickerOpen(false);
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      showError(new Error("当前浏览器不支持录音"));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recordingChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data?.size) recordingChunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        setRecording(false);
        stream.getTracks().forEach((track) => track.stop());
        const mimeType = recorder.mimeType || "audio/webm";
        const blob = new Blob(recordingChunksRef.current, { type: mimeType });
        recordingChunksRef.current = [];
        if (!blob.size) return;
        const extension = mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : "webm";
        const file = new File([blob], `voice-${Date.now()}.${extension}`, { type: mimeType });
        await sendAttachment(file, "audio");
      };
      recorder.onerror = () => showError(new Error("录音失败"));
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setEmojiPickerOpen(false);
    } catch (err) {
      setRecording(false);
      showError(err);
    }
  }

  async function sendStewardMessage(text = stewardInput) {
    const content = text.trim();
    if (!content || !stewardChannel || stewardSending) return;
    const optimistic = {
      id: `steward-local-${Date.now()}`,
      senderId: "self",
      senderName: "你",
      fromSelf: true,
      text: content,
      at: new Date().toISOString(),
      status: "发送中",
      optimistic: true,
    };
    setStewardInput("");
    setStewardOpen(true);
    setStewardSending(true);
    setError("");
    setStewardMessages((current) => [...current, optimistic]);
    try {
      await request(`/channels/${stewardChannel.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content, text: content, type: "text", mentions: [] }),
      });
      await Promise.all([loadStewardMessages(), refreshLedger()]);
    } catch (err) {
      setStewardMessages((current) => current.filter((message) => message.id !== optimistic.id));
      showError(err);
    } finally {
      setStewardSending(false);
    }
  }

  async function refreshLedger() {
    const [nextTodos, nextMemos, nextHabits, nextRelations, nextMemoryRecords, nextPersonas, brief] = await Promise.all([
      request("/todos"),
      request("/memos"),
      request("/habits"),
      request("/relations").catch(() => request("/persona-state")),
      request("/memory").catch(() => ({ facts: [], notes: [] })),
      request("/personas?include_system=true"),
      request("/steward/brief").catch(() => null),
    ]);
    setTodos(nextTodos.map(normalizeTodo));
    setMemos(nextMemos.map(normalizeMemo));
    setHabits(nextHabits.map(normalizeHabit));
    setRelations(nextRelations.map(normalizeRelation));
    setMemoryRecords(normalizeMemoryRecords(nextMemoryRecords));
    setPersonas(nextPersonas.map(normalizePersona));
    setStewardBrief(brief);
  }

  async function refreshMemoryRecords() {
    const records = await request("/memory");
    setMemoryRecords(normalizeMemoryRecords(records));
  }

  async function updateMemoryFact(factId, fields) {
    await request(`/memory/facts/${factId}`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    });
    await refreshMemoryRecords();
  }

  async function deleteMemoryFact(factId) {
    await request(`/memory/facts/${factId}`, { method: "DELETE" });
    await refreshMemoryRecords();
  }

  async function updatePersonaNote(noteId, fields) {
    await request(`/memory/persona-notes/${noteId}`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    });
    await refreshMemoryRecords();
  }

  async function deletePersonaNote(noteId) {
    await request(`/memory/persona-notes/${noteId}`, { method: "DELETE" });
    await refreshMemoryRecords();
  }

  async function createTodo(event) {
    event.preventDefault();
    if (!todoDraft.title.trim()) return;
    await request("/todos", {
      method: "POST",
      body: JSON.stringify({
        title: todoDraft.title.trim(),
        dueAt: todoDraft.dueAt || null,
        due_time: todoDraft.dueAt || null,
        priority: todoDraft.priority,
      }),
    });
    setTodoDraft({ title: "", dueAt: "", priority: "med" });
    await refreshLedger();
  }

  async function toggleTodo(todo) {
    await request(`/todos/${todo.id}`, {
      method: "PATCH",
      body: JSON.stringify({ done: !todo.done, status: todo.done ? "pending" : "done" }),
    });
    await refreshLedger();
  }

  async function deleteTodo(todo) {
    await request(`/todos/${todo.id}`, { method: "DELETE" });
    await refreshLedger();
  }

  async function clearChannel() {
    if (!activeChannel || !window.confirm("确认清空当前频道消息？")) return;
    await request(`/channels/${activeChannel.id}/messages`, { method: "DELETE" });
    setMessages([]);
  }

  async function toggleAIEnabled() {
    if (!activeChannel) return;
    const payload = await request(`/channels/${activeChannel.id}/ai_enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled: !activeChannel.aiEnabled }),
    });
    setChannels((current) =>
      current.map((channel) =>
        channel.id === activeChannel.id ? { ...channel, aiEnabled: payload.ai_enabled } : channel,
      ),
    );
  }

  async function createChannel(event) {
    event.preventDefault();
    if (!selectedPersonaIds.length && !selectedUserIds.length) return;
    const userIds = Array.from(new Set([...(currentUser ? [Number(currentUser.id)] : []), ...selectedUserIds.map(Number)]));
    const type = "group";
    const channel = await request("/channels", {
      method: "POST",
      body: JSON.stringify({
        type,
        title: type === "group" ? channelTitle || "群聊" : null,
        persona_ids: selectedPersonaIds.map(Number),
        user_ids: type === "group" ? userIds : [],
      }),
    });
    const normalized = normalizeChannel(channel);
    setChannels((current) => [normalized, ...current]);
    setActiveId(normalized.id);
    setSelectedPersonaIds([]);
    setSelectedUserIds([]);
    setChannelTitle("");
    setSheet(null);
  }

  async function refreshChannels() {
    const nextChannels = await request("/channels");
    setChannels(nextChannels.map(normalizeChannel));
  }

  async function addChannelMember(memberType, memberId) {
    if (!activeChannel) return;
    await request(`/channels/${activeChannel.id}/members`, {
      method: "POST",
      body: JSON.stringify({ member_type: memberType, member_id: Number(memberId) }),
    });
    await refreshChannels();
    await refreshLedger();
  }

  async function removeChannelMember(member) {
    if (!activeChannel) return;
    await request(`/channels/${activeChannel.id}/members/${member.memberType}/${member.id}`, {
      method: "DELETE",
    });
    await refreshChannels();
  }

  function handleComposerChange(value) {
    setInput(value);
    setMentionPickerOpen(activeChannel?.type === "group" && value.endsWith("@"));
  }

  function selectMentionMember(member) {
    setMentionedMembers((current) =>
      current.some((item) => item.channelMemberId === member.channelMemberId) ? current : [...current, member],
    );
    setInput((current) => current.replace(/@$/, `@${member.name} `));
    setMentionPickerOpen(false);
  }

  function updatePersonaField(field, value) {
    if (!activePersona) return;
    setPersonas((current) =>
      current.map((persona) => (persona.id === activePersona.id ? { ...persona, [field]: value } : persona)),
    );
  }

  async function savePersona() {
    if (!activePersona) return;
    const saved = await request(`/personas/${activePersona.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: activePersona.name,
        kind: activePersona.kind,
        core: activePersona.core,
        style: activePersona.style,
        voice: activePersona.voice,
        traits: activePersona.traits,
      }),
    });
    setPersonas((current) =>
      current.map((persona) => (persona.id === saved.id ? normalizePersona(saved) : persona)),
    );
  }

  async function createRole(event) {
    event.preventDefault();
    if (!newRoleDraft.name.trim()) return;
    const created = normalizePersona(
      await request("/personas", {
        method: "POST",
        body: JSON.stringify(newRoleDraft),
      }),
    );
    setPersonas((current) => [...current, created]);
    setActivePersonaId(created.id);
    setNewRoleDraft({ name: "", kind: "AI · 伙伴", core: "" });
    setSheet(null);
    setNav("roles");
  }

  async function deletePersona() {
    if (!activePersona || !window.confirm(`确认删除角色「${activePersona.name}」？`)) return;
    await request(`/personas/${activePersona.id}`, { method: "DELETE" });
    setPersonas((current) => {
      const next = current.filter((persona) => persona.id !== activePersona.id);
      setActivePersonaId(next[0]?.id || null);
      return next;
    });
  }

  async function startChatWithPersona(persona) {
    if (!persona) return;
    let channelId = persona.channelId;
    if (!channelId) {
      const channel = normalizeChannel(
        await request("/channels", {
          method: "POST",
          body: JSON.stringify({ type: "dm", title: null, persona_ids: [Number(persona.id)] }),
        }),
      );
      setChannels((current) => [channel, ...current]);
      channelId = channel.id;
      setPersonas((current) =>
        current.map((item) => (item.id === persona.id ? { ...item, channelId } : item)),
      );
    }
    setActiveId(channelId);
    setNav("chat");
  }

  const stats = summarizeTodos(todos);
  const schedule = buildSchedule(todos);
  const focusTodo = todos.find((todo) => !todo.done && todo.priority === "high") || todos.find((todo) => !todo.done);
  const activeMembers = activeChannel?.members?.map(memberLabel).join("、") || "暂无成员";

  if (!currentUser) {
    return (
      <main className="identity-root" data-theme={theme} data-accent={accent}>
        <form className="identity-card" onSubmit={chooseIdentity}>
          <div className="brand-mark">C</div>
          <h1>选择你的名字</h1>
          <p>本地薄身份，无密码。两个人用不同名字进入同一频道即可测试 v6。</p>
          <input
            value={identityDraft}
            onChange={(event) => setIdentityDraft(event.target.value)}
            placeholder="例如：小舒"
            autoFocus
          />
          <button disabled={!identityDraft.trim()}>进入</button>
        </form>
      </main>
    );
  }

  return (
    <main className={collapsed ? "app-root collapsed" : "app-root"} data-theme={theme} data-accent={accent}>
      <aside className={collapsed ? "channel-rail collapsed" : "channel-rail"}>
        <div className="brand-row">
          {!collapsed && (
            <div className="brand-lockup">
              <div className="brand-mark">C</div>
              <div>
                <h1>Companion</h1>
                <p>v3 · 在线</p>
              </div>
            </div>
          )}
          <button
            className="icon-button"
            onClick={() => setCollapsed((value) => !value)}
            title={collapsed ? "展开侧栏" : "收起侧栏"}
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          >
            {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          </button>
        </div>

        <div className="rail-nav">
          <button className={nav === "chat" ? "active" : ""} onClick={() => setNav("chat")} title="对话">
            <Bell size={16} />
            {!collapsed && <span>对话</span>}
          </button>
          <button className={nav === "roles" ? "active" : ""} onClick={() => setNav("roles")} title="角色">
            <Circle size={16} />
            {!collapsed && <span>角色</span>}
          </button>
        </div>

        <div className="channel-list-wrap">
          {nav === "chat" && (
            <>
              <button className="new-channel" onClick={() => setSheet("create")}>
                <Plus size={18} />
                {!collapsed && <span>新建频道</span>}
              </button>
              {!collapsed && <div className="rail-label">对话</div>}
              <div className="channel-list">
                {chatChannels.map((channel) => (
                  <button
                    key={channel.id}
                    className={channel.id === activeChannel?.id ? "channel-row active" : "channel-row"}
                    onClick={() => setActiveId(channel.id)}
                  >
                    <Avatar name={channel.title} hue={channel.avatarHue} />
                    {!collapsed && (
                      <div className="channel-copy">
                        <div className="channel-line">
                          <strong>{channel.title}</strong>
                          <span>{formatShortTime(channel.lastMessage?.at)}</span>
                        </div>
                        <p>{channel.lastMessage?.text || channel.members.map((m) => m.name).join("、")}</p>
                      </div>
                    )}
                    {!collapsed && channel.unread > 0 && <span className="unread">{channel.unread}</span>}
                  </button>
                ))}
              </div>
            </>
          )}
          {nav === "roles" && (
            <>
              <button className="new-channel" onClick={() => setSheet("roleCreate")}>
                <Plus size={18} />
                {!collapsed && <span>新建角色</span>}
              </button>
              {!collapsed && <div className="rail-label">角色</div>}
              <div className="channel-list">
                {personas.map((persona) => (
                  <button
                    key={persona.id}
                    className={persona.id === activePersona?.id ? "channel-row active" : "channel-row"}
                    onClick={() => setActivePersonaId(persona.id)}
                  >
                    <Avatar name={persona.name} hue={persona.avatarHue} />
                    {!collapsed && (
                      <div className="channel-copy">
                        <div className="channel-line">
                          <strong>{persona.name}</strong>
                        </div>
                        <p>{persona.kind}</p>
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {!collapsed && (
          <div className="account-row">
            <Avatar name={currentUser.display_name || "我"} hue={280} />
            <div>
              <strong>{currentUser.display_name}</strong>
              <p>User #{currentUser.id}</p>
            </div>
            <button className="icon-button small logout-button" onClick={handleLogout} title="退出登录" aria-label="退出登录">
              <LogOut size={15} />
            </button>
          </div>
        )}
      </aside>

      <section className="main-pane">
        {nav === "chat" && (
          <>
        <header className="topbar">
          <div className="active-title">
            <Avatar name={activeChannel?.title || "C"} hue={activeChannel?.avatarHue || 95} />
            <div>
              <h2>{activeChannel?.title || "频道"}</h2>
              <p>{activeMembers}</p>
            </div>
          </div>
          <div className="topbar-actions">
            <div className="topbar-popover-wrap">
              <button
                className={sheet === "members" ? "topbar-entry active" : "topbar-entry"}
                onClick={() => setSheet(sheet === "members" ? null : "members")}
                aria-label="群聊管理"
                aria-expanded={sheet === "members"}
                disabled={!activeChannel}
              >
                <Users size={16} />
                <span>群聊</span>
              </button>
              <MemberSheet
                open={sheet === "members"}
                onOpenChange={(open) => setSheet(open ? "members" : null)}
                channel={activeChannel}
                personas={personas}
                users={users}
                currentUser={currentUser}
                onAdd={addChannelMember}
                onRemove={removeChannelMember}
                onToggleAI={toggleAIEnabled}
                onClear={clearChannel}
              />
            </div>
            <div className="topbar-popover-wrap">
              <button
                className={sheet === "workbench" ? "topbar-entry active" : "topbar-entry"}
                onClick={() => setSheet(sheet === "workbench" ? null : "workbench")}
                aria-label="事项"
                aria-expanded={sheet === "workbench"}
              >
                <Check size={16} />
                <span>事项</span>
                {stats.pending > 0 && <em>{stats.pending}</em>}
              </button>
              {sheet === "workbench" && (
                <TopPopover title="事项" onClose={() => setSheet(null)} className="workbench-popover">
                  <div className="tabs top-popover-tabs">
                    {[
                      ["today", "今日", null],
                      ["tasks", "事项", String(stats.pending)],
                      ["memory", "记忆", null],
                    ].map(([key, label, badge]) => (
                      <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
                        {label}
                        {badge && <span>{badge}</span>}
                      </button>
                    ))}
                  </div>
                  <div className="top-popover-scroll">
                    <div className="side-panel-anim" key={tab}>
                      {tab === "today" && (
                        <TodayPanel
                          brief={stewardBrief}
                          focusTodo={focusTodo}
                          schedule={schedule}
                          stats={stats}
                          habits={habits}
                          onStart={() => focusTodo && sendMessage(`我准备去做：${focusTodo.title}`)}
                        />
                      )}
                      {tab === "tasks" && (
                        <TasksPanel
                          todos={todos}
                          draft={todoDraft}
                          setDraft={setTodoDraft}
                          onCreate={createTodo}
                          onToggle={toggleTodo}
                          onDelete={deleteTodo}
                        />
                      )}
                      {tab === "memory" && (
                        <MemoryPanel
                          memos={memos}
                          habits={habits}
                          relations={relations}
                          records={memoryRecords}
                          predicateMeta={memoryPredicates}
                          onRefresh={refreshMemoryRecords}
                          onUpdateFact={updateMemoryFact}
                          onDeleteFact={deleteMemoryFact}
                          onUpdateNote={updatePersonaNote}
                          onDeleteNote={deletePersonaNote}
                        />
                      )}
                    </div>
                  </div>
                </TopPopover>
              )}
            </div>
            <div className="topbar-popover-wrap">
              <button
                className={sheet === "steward" ? "topbar-entry active" : "topbar-entry"}
                onClick={() => setSheet(sheet === "steward" ? null : "steward")}
                aria-label="管家对话"
                aria-expanded={sheet === "steward"}
                disabled={!stewardChannel}
              >
                <Bell size={16} />
                <span>管家</span>
              </button>
              {sheet === "steward" && stewardChannel && (
                <div className="top-popover steward-popover">
                  <StewardDock
                    brief={stewardBrief}
                    open
                    onToggle={() => setSheet(null)}
                    messages={stewardMessages}
                    typing={stewardTyping}
                    input={stewardInput}
                    setInput={setStewardInput}
                    sending={stewardSending}
                    onSend={sendStewardMessage}
                    endRef={stewardEndRef}
                  />
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="workspace">
          <section className="chat-pane">
            <div className="message-list">
              {withDateSeparators(messages).map((item) =>
                item.kind === "date" ? (
                  <div className="date-separator" key={item.id}>
                    <span>{item.text}</span>
                  </div>
                ) : (
                  <MessageBubble
                    key={item.id}
                    message={item}
                    showName={activeChannel?.type === "group" && !item.fromSelf}
                  />
                ),
              )}
              {typing && <TypingBubble channel={activeChannel} />}
              <div ref={messageEndRef} />
            </div>

            <div className="composer">
              <div className="suggestions">
                {(activeChannel?.type === "group"
                  ? ["@角色 收到", "定个时间"]
                  : ["排进事项", "稍后提醒我"]
                ).map((text) => (
                  <button key={text} onClick={() => sendMessage(text)} disabled={!activeChannel || sending}>
                    {text}
                  </button>
                ))}
                {activeChannel?.type === "group" && <span>AI 默认沉默，@ 或点名更容易触发</span>}
              </div>
              {(mentionedMembers.length > 0 || mentionPickerOpen) && (
                <div className="mention-strip">
                  {mentionedMembers.map((member) => (
                    <button
                      type="button"
                      key={member.channelMemberId}
                      onClick={() =>
                        setMentionedMembers((current) =>
                          current.filter((item) => item.channelMemberId !== member.channelMemberId),
                        )
                      }
                    >
                      @{member.name}
                      <X size={12} />
                    </button>
                  ))}
                  {mentionPickerOpen && (
                    <div className="mention-menu">
                      {mentionableMembers.length ? (
                        mentionableMembers.map((member) => (
                          <button type="button" key={member.channelMemberId} onClick={() => selectMentionMember(member)}>
                            {memberLabel(member)}
                          </button>
                        ))
                      ) : (
                        <span>暂无可 @ 的 AI 成员</span>
                      )}
                    </div>
                  )}
                </div>
              )}
              <form
                className="composer-box"
                onSubmit={(event) => {
                  event.preventDefault();
                  sendMessage();
                }}
              >
                <IconShell title="附件" onClick={() => fileInputRef.current?.click()} disabled={!activeChannel || sending}>
                  <Paperclip size={19} />
                </IconShell>
                <IconShell title="图片" onClick={() => imageInputRef.current?.click()} disabled={!activeChannel || sending}>
                  <Image size={19} />
                </IconShell>
                <input
                  ref={fileInputRef}
                  className="hidden-file-input"
                  type="file"
                  onChange={(event) => sendFile(event.target.files?.[0])}
                />
                <input
                  ref={imageInputRef}
                  className="hidden-file-input"
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  onChange={(event) => sendImage(event.target.files?.[0])}
                />
                <input
                  value={input}
                  onChange={(event) => handleComposerChange(event.target.value)}
                  placeholder={activeChannel?.type === "group" ? "发给频道里的真人；AI 默认旁听…" : "说点什么…"}
                  disabled={!activeChannel || sending}
                />
                <div className="emoji-anchor">
                  <IconShell
                    title="表情"
                    onClick={() => setEmojiPickerOpen((open) => !open)}
                    disabled={!activeChannel || sending}
                  >
                    <Smile size={19} />
                  </IconShell>
                  {emojiPickerOpen && (
                    <div className="emoji-menu">
                      {EMOJI_CHOICES.map((emoji) => (
                        <button type="button" key={emoji} onClick={() => insertEmoji(emoji)}>
                          {emoji}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <IconShell
                  title={recording ? "停止录音" : "语音"}
                  onClick={toggleRecording}
                  active={recording}
                  disabled={!activeChannel || sending}
                >
                  {recording ? <Square size={17} /> : <Mic size={19} />}
                </IconShell>
                <button className="send-button" disabled={!input.trim() || sending}>
                  <Send size={16} />
                  发送
                </button>
              </form>
            </div>
          </section>
        </div>
          </>
        )}
        {nav === "roles" && (
          <RolePage
            activePersona={activePersona}
            updatePersonaField={updatePersonaField}
            savePersona={savePersona}
            deletePersona={deletePersona}
            startChatWithPersona={startChatWithPersona}
            users={users}
          />
        )}
      </section>

      <CreateChannelDialog
        open={sheet === "create"}
        onOpenChange={(open) => setSheet(open ? "create" : null)}
        personas={regularPersonas}
        users={users}
        currentUser={currentUser}
        selectedIds={selectedPersonaIds}
        setSelectedIds={setSelectedPersonaIds}
        selectedUserIds={selectedUserIds}
        setSelectedUserIds={setSelectedUserIds}
        title={channelTitle}
        setTitle={setChannelTitle}
        onSubmit={createChannel}
      />
      <CreateRoleDialog
        open={sheet === "roleCreate"}
        onOpenChange={(open) => setSheet(open ? "roleCreate" : null)}
        draft={newRoleDraft}
        setDraft={setNewRoleDraft}
        onSubmit={createRole}
      />
      {error && (
        <div className="toast">
          <span>{error}</span>
          <button onClick={() => setError("")}><X size={14} /></button>
        </div>
      )}
    </main>
  );
}

function Avatar({ name, hue = 95 }) {
  return (
    <div className="avatar" style={{ "--hue": hue }}>
      {initial(name)}
    </div>
  );
}

function RolePage({
  activePersona,
  updatePersonaField,
  savePersona,
  deletePersona,
  startChatWithPersona,
  users,
}) {
  if (!activePersona) {
    return (
      <div className="role-page">
        <header className="topbar">
          <h2>角色档案</h2>
        </header>
        <Empty text="暂无角色" />
      </div>
    );
  }
  const pct = Math.round((activePersona.familiarity || 0) * 100);
  const stats = activePersona.stats || {};
  return (
    <div className="role-page">
      <header className="topbar">
        <h2>角色档案</h2>
      </header>
      <div className="role-scroll">
        <div className="role-card">
          <div className="role-hero">
            <Avatar name={activePersona.name} hue={activePersona.avatarHue} />
            <div>
              <h2>{activePersona.name}</h2>
              <p>{activePersona.kind}</p>
              <p>{personaOwnerLabel(activePersona, users)}</p>
              <div className="role-familiarity">
                <div><span key={activePersona.id} style={{ width: `${pct}%` }} /></div>
                <em>熟悉度 {pct}%</em>
              </div>
            </div>
            <button onClick={() => startChatWithPersona(activePersona)}>发起对话</button>
          </div>

          <div className="role-stats">
            <Stat value={stats.messages || "0"} label="消息" />
            <Stat value={stats.sharedTasks || "0"} label="共同事项" />
            <Stat value={stats.lastInteraction || "暂无"} label="最近互动" />
          </div>

          <label className="role-field">
            <span>核心设定</span>
            <textarea
              value={activePersona.core}
              onChange={(event) => updatePersonaField("core", event.target.value)}
            />
          </label>
          <label className="role-field">
            <span>说话风格</span>
            <textarea
              className="compact"
              value={activePersona.style}
              onChange={(event) => updatePersonaField("style", event.target.value)}
            />
          </label>
          <label className="role-field">
            <span>声音</span>
            <input
              value={activePersona.voice}
              onChange={(event) => updatePersonaField("voice", event.target.value)}
            />
          </label>
          <TagEditor
            traits={activePersona.traits}
            onChange={(traits) => updatePersonaField("traits", traits)}
          />
          <div className="role-actions">
            <button onClick={savePersona}>保存角色卡</button>
            <button onClick={deletePersona}>删除角色</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TagEditor({ traits, onChange }) {
  const [draft, setDraft] = useState("");
  function addTag(event) {
    event.preventDefault();
    const value = draft.trim();
    if (!value) return;
    onChange([...(traits || []), value]);
    setDraft("");
  }
  return (
    <div className="role-field">
      <span>性格标签</span>
      <div className="trait-row">
        {(traits || []).map((trait, index) => (
          <button
            type="button"
            key={`${trait}-${index}`}
            title="点击移除"
            onClick={() => onChange(traits.filter((_, itemIndex) => itemIndex !== index))}
          >
            {trait}
          </button>
        ))}
        <form onSubmit={addTag}>
          <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="+ 标签" />
        </form>
      </div>
    </div>
  );
}

function IconShell({ title, children, onClick, active = false, disabled = false }) {
  return (
    <button
      type="button"
      className={active ? "composer-icon active" : "composer-icon"}
      title={title}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

function MessageBubble({ message, showName }) {
  const content = <BubbleContent message={message} />;
  if (message.fromSelf) {
    return (
      <div className="message-row outgoing">
        <div className="bubble-stack">
          <div className="bubble user">{content}</div>
          <span>{formatShortTime(message.at)} · {message.status || "已送达"}</span>
        </div>
      </div>
    );
  }
  return (
    <div className={`message-row incoming ${message.authorType === "human" ? "other-human" : "ai-author"}`}>
      <Avatar name={message.senderName} hue={message.avatarHue} />
      <div className="bubble-stack">
        {showName && <em>{message.senderName}</em>}
        <div className={`bubble ${message.authorType === "human" ? "human" : "ai"}`}>{content}</div>
        <span>{formatShortTime(message.at)}</span>
      </div>
    </div>
  );
}

function BubbleContent({ message }) {
  return (
    <>
      {message.type === "image" && message.mediaUrl && (
        <img className="bubble-image" src={message.mediaUrl} alt={message.fileName || "上传图片"} />
      )}
      {message.type === "audio" && message.mediaUrl && (
        <audio className="bubble-audio" controls src={message.mediaUrl}>
          <a href={message.mediaUrl}>{message.fileName || "语音消息"}</a>
        </audio>
      )}
      {message.type === "file" && message.mediaUrl && (
        <a className="bubble-file" href={message.mediaUrl} download={message.fileName || undefined}>
          <FileText size={18} />
          <span>{message.fileName || "附件"}</span>
        </a>
      )}
      {message.text && <div>{message.text}</div>}
      {message.type === "image" && !message.text && <div className="media-caption">{message.fileName || "图片"}</div>}
      {message.type === "audio" && !message.text && <div className="media-caption">{message.fileName || "语音"}</div>}
    </>
  );
}

function TypingBubble({ channel }) {
  return (
    <div className="message-row incoming">
      <Avatar name={channel?.title || "管"} hue={channel?.avatarHue || 95} />
      <div className="typing-bubble">
        <i />
        <i />
        <i />
      </div>
    </div>
  );
}

function TodayPanel({ brief, focusTodo, schedule, stats, habits, onStart }) {
  const now = new Date();
  return (
    <>
      <section className="side-heading">
        <h3>{brief?.greeting || greeting()}</h3>
        <p>{now.toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "long" })}</p>
      </section>
      <section className="steward-note">
        <Avatar name="管" hue={280} />
        <div>
          <strong>管家提醒</strong>
          <p>{brief?.note || `今天还有 ${stats.pending} 件待办，其中 ${stats.high} 件高优先级。`}</p>
        </div>
      </section>
      <section className="focus-card">
        <div>
          <h4>{focusTodo?.title || "今天暂无焦点事项"}</h4>
          <p>{focusTodo ? todoMeta(focusTodo) : "可以从事项页添加一个安排"}</p>
        </div>
        {focusTodo && <button onClick={onStart}>出发</button>}
      </section>
      <section className="side-section">
        <h4>今日日程</h4>
        <div className="timeline">
          {schedule.map((event) => (
            <div className={`timeline-row ${event.state}`} key={event.id}>
              <time>{formatHour(event.at)}</time>
              <Circle size={11} />
              <div>
                <strong>{event.title}</strong>
                {event.tag && <p>{event.tag}</p>}
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="stat-grid">
        <Stat value={stats.pending} label="待办" />
        <Stat value={stats.done} label="已完成" />
        <Stat value={habits[0]?.streak || 0} label="习惯连续(天)" />
      </section>
    </>
  );
}

function TasksPanel({ todos, draft, setDraft, onCreate, onToggle, onDelete }) {
  return (
    <>
      <form className="task-create" onSubmit={onCreate}>
        <input
          value={draft.title}
          onChange={(event) => setDraft({ ...draft, title: event.target.value })}
          placeholder="新建待办"
        />
        <div>
          <input
            value={draft.dueAt}
            onChange={(event) => setDraft({ ...draft, dueAt: event.target.value })}
            placeholder="今天 15:00 / 2026-06-26T15:00"
          />
          <select
            value={draft.priority}
            onChange={(event) => setDraft({ ...draft, priority: event.target.value })}
          >
            <option value="high">高</option>
            <option value="med">中</option>
            <option value="low">低</option>
          </select>
        </div>
        <button>添加</button>
      </form>
      <div className="todo-list">
        {todos.map((todo) => (
          <article className={`todo-card priority-${todo.priority} ${todo.done ? "done" : ""}`} key={todo.id}>
            <button className="check-button" onClick={() => onToggle(todo)}>
              {todo.done && <Check size={13} />}
            </button>
            <div>
              <h4>{todo.title}</h4>
              <p>{todoMeta(todo)}</p>
              {todo.notes && <span>{todo.notes}</span>}
              {todo.repeat && <span>重复：{todo.repeat}</span>}
            </div>
            <button className="delete-button" onClick={() => onDelete(todo)}>
              <Trash2 size={14} />
            </button>
          </article>
        ))}
        {!todos.length && <Empty text="暂无事项" />}
      </div>
    </>
  );
}

function MemoryPanel({
  memos,
  habits,
  relations,
  records,
  predicateMeta,
  onRefresh,
  onUpdateFact,
  onDeleteFact,
  onUpdateNote,
  onDeleteNote,
}) {
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const facts = records?.facts || [];
  const notes = records?.notes || [];
  const groupOrder = predicateMeta?.groupOrder || [];
  const predicates = predicateMeta?.predicates || {};
  const groupedFacts = groupMemoryFacts(facts, groupOrder, predicates);

  function startEdit(kind, item) {
    setEditing(`${kind}:${item.id}`);
    setDraft(item.content || "");
  }

  async function saveEdit(kind, id) {
    const content = draft.trim();
    if (!content) return;
    setSaving(true);
    try {
      if (kind === "fact") {
        await onUpdateFact(id, { content });
      } else {
        await onUpdateNote(id, { content });
      }
      setEditing(null);
      setDraft("");
    } catch (err) {
      window.alert(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  async function deleteItem(kind, id) {
    if (!window.confirm("确认删除这条记忆？")) return;
    try {
      if (kind === "fact") {
        await onDeleteFact(id);
      } else {
        await onDeleteNote(id);
      }
    } catch (err) {
      window.alert(err.message || String(err));
    }
  }

  return (
    <>
      <section className="side-section">
        <h4>备忘录</h4>
        <div className="memo-list">
          {memos.map((memo) => <p key={memo.id}>{memo.text}</p>)}
          {!memos.length && <Empty text="暂无备忘" />}
        </div>
      </section>
      <section className="side-section">
        <h4>习惯追踪</h4>
        {habits.map((habit) => (
          <article className="habit-card" key={habit.id}>
            <div>
              <strong>{habit.name}</strong>
              <p>{habit.remindAt || habit.schedule}</p>
            </div>
            <span>{habit.streak} 天</span>
            <div className="habit-days">
              {habit.last7days.map((done, index) => <i className={done ? "done" : ""} key={index} />)}
            </div>
          </article>
        ))}
        {!habits.length && <Empty text="暂无习惯" />}
      </section>
      <section className="side-section">
        <h4>关系</h4>
        {relations.map((relation) => (
          <article className="relation-card" key={relation.id}>
            <Avatar name={relation.name} hue={relation.avatarHue} />
            <div>
              <strong>{relation.name}</strong>
              <p>{relation.role || "伙伴"}</p>
              <div className="progress"><i style={{ width: `${Math.round(relation.familiarity * 100)}%` }} /></div>
            </div>
            <span>{Math.round(relation.familiarity * 100)}%</span>
          </article>
        ))}
        {!relations.length && <Empty text="暂无关系状态" />}
      </section>
      <section className="side-section memory-admin">
        <div className="memory-admin-head">
          <h4>结构化事实</h4>
          <button type="button" onClick={onRefresh}>刷新</button>
        </div>
        {groupedFacts.map((group) => (
          <details className="memory-group" key={group.name} open>
            <summary>
              <span>{group.name}</span>
              <button type="button" disabled title="后续支持手动添加">+</button>
            </summary>
            <div className="memory-record-list">
              {group.items.map((fact) => {
                const key = `fact:${fact.id}`;
                const active = editing === key;
                return (
                  <article className="memory-record" key={key}>
                    <div className="memory-record-meta">
                      <strong>{fact.predicateLabel}</strong>
                      <span>置信度 {formatConfidence(fact.confidence)} · {formatShortTime(fact.createdAt)}</span>
                    </div>
                    {active ? (
                      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
                    ) : (
                      <p>{fact.content}</p>
                    )}
                    <div className="memory-record-actions">
                      {active ? (
                        <>
                          <button type="button" onClick={() => saveEdit("fact", fact.id)} disabled={saving || !draft.trim()}>
                            保存
                          </button>
                          <button type="button" onClick={() => setEditing(null)} disabled={saving}>取消</button>
                        </>
                      ) : (
                        <>
                          <button type="button" onClick={() => startEdit("fact", fact)}>编辑</button>
                          <button type="button" onClick={() => deleteItem("fact", fact.id)}>删除</button>
                        </>
                      )}
                    </div>
                  </article>
                );
              })}
              {!group.items.length && <p className="memory-empty">管家会在对话中自动提炼，也可以手动添加</p>}
            </div>
          </details>
        ))}
      </section>
      <section className="side-section memory-admin">
        <div className="memory-admin-head">
          <h4>角色笔记</h4>
        </div>
        <div className="memory-record-list">
          {notes.map((note) => {
            const key = `note:${note.id}`;
            const active = editing === key;
            return (
              <article className="memory-record" key={key}>
                <div className="memory-record-meta">
                  <strong>{note.personaName}</strong>
                  <span>{formatShortTime(note.updatedAt)}</span>
                </div>
                {active ? (
                  <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
                ) : (
                  <p>{note.content}</p>
                )}
                <div className="memory-record-actions">
                  {active ? (
                    <>
                      <button type="button" onClick={() => saveEdit("note", note.id)} disabled={saving || !draft.trim()}>
                        保存
                      </button>
                      <button type="button" onClick={() => setEditing(null)} disabled={saving}>取消</button>
                    </>
                  ) : (
                    <>
                      <button type="button" onClick={() => startEdit("note", note)}>编辑</button>
                      <button type="button" onClick={() => deleteItem("note", note.id)}>删除</button>
                    </>
                  )}
                </div>
              </article>
            );
          })}
          {!notes.length && <Empty text="暂无角色笔记" />}
        </div>
      </section>
    </>
  );
}

function StewardDock({
  brief,
  open,
  onToggle,
  messages,
  typing,
  input,
  setInput,
  sending,
  onSend,
  endRef,
}) {
  const chips = brief?.quickChips?.length ? brief.quickChips : ["梳理明天", "只看高优先级"];
  const lastIncoming = [...messages].reverse().find((message) => !message.fromSelf);
  return (
    <section className={open ? "steward-panel open" : "steward-panel"}>
      <button className="steward-panel-head" onClick={onToggle}>
        <span className="steward-head-main">
          <Bell size={16} />
          <strong>管家</strong>
        </span>
        <span className="steward-head-preview">
          {open ? "收起" : lastIncoming?.text || brief?.note || "打开管家对话"}
        </span>
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="steward-panel-body">
          <div className="steward-mini-messages">
            {withDateSeparators(messages).map((item) =>
              item.kind === "date" ? (
                <div className="steward-mini-date" key={item.id}>{item.text}</div>
              ) : (
                <div
                  className={item.fromSelf ? "steward-mini-row outgoing" : "steward-mini-row incoming"}
                  key={item.id}
                >
                  <div>{item.text}</div>
                </div>
              ),
            )}
            {typing && (
              <div className="steward-mini-row incoming">
                <div className="steward-mini-typing"><i /><i /><i /></div>
              </div>
            )}
            {!messages.length && (
              <div className="steward-empty">{brief?.note || "我在这里，随时可以帮你整理安排。"}</div>
            )}
            <div ref={endRef} />
          </div>
          <div className="steward-chip-row">
            {chips.map((chip) => (
              <button key={chip} onClick={() => onSend(chip)} disabled={sending}>
                {chip}
              </button>
            ))}
          </div>
          <form
            className="steward-input"
            onSubmit={(event) => {
              event.preventDefault();
              onSend();
            }}
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="和管家说点什么…"
              disabled={sending}
            />
            <button disabled={!input.trim() || sending}>
              <Send size={14} />
            </button>
          </form>
        </div>
      )}
    </section>
  );
}

function TopPopover({ title, onClose, className = "", children }) {
  return (
    <div className={`top-popover ${className}`}>
      <div className="top-popover-head">
        <strong>{title}</strong>
        <button type="button" onClick={onClose} title="关闭" aria-label={`关闭${title}`}>
          <X size={14} />
        </button>
      </div>
      {children}
    </div>
  );
}

function CreateChannelDialog({
  open,
  onOpenChange,
  personas,
  users,
  currentUser,
  selectedIds,
  setSelectedIds,
  selectedUserIds,
  setSelectedUserIds,
  title,
  setTitle,
  onSubmit,
}) {
  function toggle(id) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }
  function toggleUser(id) {
    setSelectedUserIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }
  const visiblePersonas = personas.filter(
    (persona) => !persona.ownerUserId || Number(persona.ownerUserId) === Number(currentUser?.id),
  );
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Overlay className="sheet-overlay" />
      <Dialog.Content className="modal">
        <Dialog.Title>拉人建群</Dialog.Title>
        <form onSubmit={onSubmit}>
          <label>
            群聊标题
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：周末约饭" />
          </label>
          <div className="persona-options">
            <strong>真人成员</strong>
            {users.map((user) => (
              <label key={user.id}>
                <input
                  type="checkbox"
                  checked={Number(user.id) === Number(currentUser?.id) || selectedUserIds.includes(user.id)}
                  disabled={Number(user.id) === Number(currentUser?.id)}
                  onChange={() => toggleUser(user.id)}
                />
                {user.display_name || user.name}·真人
              </label>
            ))}
          </div>
          <div className="persona-options">
            <strong>AI 成员</strong>
            {visiblePersonas.map((persona) => (
              <label key={persona.id}>
                <input type="checkbox" checked={selectedIds.includes(persona.id)} onChange={() => toggle(persona.id)} />
                {personaOwnerLabel(persona, users)}
              </label>
            ))}
          </div>
          <div className="modal-actions">
            <Dialog.Close asChild><button type="button">取消</button></Dialog.Close>
            <button disabled={!selectedIds.length && !selectedUserIds.length}>创建</button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function MemberSheet({
  open,
  onOpenChange,
  channel,
  personas,
  users,
  currentUser,
  onAdd,
  onRemove,
  onToggleAI,
  onClear,
}) {
  const [tab, setTab] = useState("humans");
  const [query, setQuery] = useState("");
  if (!open) return null;
  const existing = new Set((channel?.members || []).map((member) => `${member.memberType}:${member.id}`));
  const normalizedQuery = query.trim().toLowerCase();
  const isCreator = Number(channel?.createdByUserId) === Number(currentUser?.id);
  const matches = (value) => String(value || "").toLowerCase().includes(normalizedQuery);
  const humans = users.filter(
    (user) =>
      Number(user.id) !== Number(currentUser?.id) &&
      !existing.has(`human:${user.id}`) &&
      (!normalizedQuery || matches(user.display_name || user.name)),
  );
  const availablePersonas = personas.filter(
    (persona) => !existing.has(`agent:${persona.id}`) && (!normalizedQuery || matches(persona.name)),
  );
  const myAi = availablePersonas.filter(
    (persona) =>
      (persona.personaKind === "owned" && Number(persona.creatorUserId) === Number(currentUser?.id)) ||
      (persona.personaKind === "system" && Number(persona.ownerUserId || persona.creatorUserId) === Number(currentUser?.id)),
  );
  const entertainmentAi = availablePersonas.filter((persona) => persona.personaKind === "entertainment");
  const removable = (member) => {
    if (isCreator) return true;
    if (member.memberType === "human") return Number(member.id) === Number(currentUser?.id);
    return Number(member.ownerUserId) === Number(currentUser?.id);
  };
  const addAndKeepOpen = async (memberType, memberId) => {
    await onAdd(memberType, memberId);
  };
  const removeAndKeepOpen = async (member) => {
    await onRemove(member);
  };
  return (
    <div className="member-popover">
      <div className="member-popover-head">
        <strong>群聊管理</strong>
        <button type="button" onClick={() => onOpenChange(false)} title="关闭">
          <X size={14} />
        </button>
      </div>
      <div className="channel-tools">
        <button type="button" onClick={onToggleAI} disabled={!channel}>
          {channel?.aiEnabled ? "AI 在场" : "AI 缺席"}
        </button>
        <button type="button" className="danger" onClick={onClear} disabled={!channel}>
          清空消息
        </button>
      </div>
      <div className="member-tabs">
        <button className={tab === "humans" ? "active" : ""} onClick={() => setTab("humans")}>
          真人
        </button>
        <button className={tab === "ai" ? "active" : ""} onClick={() => setTab("ai")}>
          AI
        </button>
      </div>
      <input
        className="member-search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="搜索成员"
      />
      <div className="member-popover-body">
        <section>
          <div className="member-section-title">当前成员</div>
          {(channel?.members || []).map((member) => (
            <div className="member-row compact" key={`${member.memberType}-${member.id}`}>
              <span>{memberLabel(member)}</span>
              <button
                disabled={!removable(member)}
                title={!removable(member) ? "只有频道创建者或该成员可以移除" : "移除成员"}
                onClick={() => removeAndKeepOpen(member)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </section>
        {tab === "humans" && (
          <section>
            <div className="member-section-title">真人</div>
            {humans.length ? (
              humans.map((user) => (
                <button className="member-pick" key={user.id} onClick={() => addAndKeepOpen("human", user.id)}>
                  <Avatar name={user.display_name || user.name} hue={hueFor(user.display_name || user.name)} />
                  <span>{user.display_name || user.name}</span>
                </button>
              ))
            ) : (
              <div className="member-empty">没有可添加的真人</div>
            )}
          </section>
        )}
        {tab === "ai" && (
          <>
            <section>
              <div className="member-section-title">我的 AI</div>
              {myAi.length ? (
                myAi.map((persona) => (
                  <button className="member-pick" key={persona.id} onClick={() => addAndKeepOpen("agent", persona.id)}>
                    <Avatar name={persona.name} hue={persona.avatarHue} />
                    <span>{personaOwnerLabel(persona, users)}</span>
                    {persona.personaKind === "system" && <em><Star size={12} /> 管家</em>}
                  </button>
                ))
              ) : (
                <div className="member-empty">没有可添加的自有 AI</div>
              )}
            </section>
            <section>
              <div className="member-section-title">娱乐 AI</div>
              {entertainmentAi.length ? (
                entertainmentAi.map((persona) => (
                  <button className="member-pick" key={persona.id} onClick={() => addAndKeepOpen("agent", persona.id)}>
                    <Avatar name={persona.name} hue={persona.avatarHue} />
                    <span>{persona.name}</span>
                  </button>
                ))
              ) : (
                <div className="member-empty">没有可添加的娱乐 AI</div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function CreateRoleDialog({ open, onOpenChange, draft, setDraft, onSubmit }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Overlay className="sheet-overlay" />
      <Dialog.Content className="modal">
        <Dialog.Title>新建角色</Dialog.Title>
        <form onSubmit={onSubmit}>
          <label>
            名称
            <input
              value={draft.name}
              onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
              placeholder="例如：小柚"
            />
          </label>
          <label>
            类型标签
            <input
              value={draft.kind}
              onChange={(event) => setDraft((current) => ({ ...current, kind: event.target.value }))}
              placeholder="AI · 伙伴"
            />
          </label>
          <label>
            核心设定
            <textarea
              value={draft.core}
              onChange={(event) => setDraft((current) => ({ ...current, core: event.target.value }))}
              placeholder="这个角色是谁、和你是什么关系、擅长什么。"
            />
          </label>
          <div className="modal-actions">
            <Dialog.Close asChild><button type="button">取消</button></Dialog.Close>
            <button disabled={!draft.name.trim()}>创建</button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function Stat({ value, label }) {
  return (
    <div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Empty({ text }) {
  return <div className="empty">{text}</div>;
}

function normalizeChannel(channel) {
  const members = (channel.members || []).map((member) => ({
    id: member.id,
    channelMemberId: member.channel_member_id || member.channelMemberId,
    memberType: member.member_type || "persona",
    name: member.name,
    rawName: member.raw_name || member.rawName || member.name,
    role: member.role || member.model_role || (member.is_system ? "管家" : "伙伴"),
    avatarHue: member.avatarHue ?? hueFor(member.name || String(member.id)),
    isAgent: member.isAgent ?? member.member_type !== "human",
    is_system: member.is_system,
    ownerUserId: member.owner_user_id ?? member.ownerUserId ?? null,
  }));
  const title = channel.title || members.map((member) => member.name).join("、") || "频道";
  return {
    id: channel.id,
    type: channel.type,
    title,
    members,
    is_system: channel.is_system,
    createdByUserId: channel.created_by_user_id ?? channel.createdByUserId ?? null,
    aiEnabled: channel.ai_enabled ?? true,
    avatarHue: channel.avatarHue ?? (members[0]?.avatarHue || hueFor(title)),
    lastMessage: channel.lastMessage || null,
    unread: channel.unread || 0,
  };
}

function normalizeMessage(message) {
  const currentUserId = Number(sessionStorage.getItem("user_id") || 0);
  const authorType = message.author_type || (message.sender === "persona" ? "ai" : "human");
  const authorUserId = message.author_user_id || null;
  const fromSelf = message.fromSelf ?? (authorType === "human" && Number(authorUserId) === currentUserId);
  const senderName =
    message.senderName ||
    message.author_user_name ||
    message.persona_name ||
    (fromSelf ? "你" : authorType === "human" ? "对方" : "角色");
  return {
    id: message.id,
    senderId: message.senderId || message.persona_id || authorUserId || (fromSelf ? "self" : "agent"),
    senderName,
    avatarHue: message.avatarHue ?? hueFor(senderName),
    fromSelf,
    authorType,
    authorUserId,
    type: message.type || "text",
    text: message.text || message.content || "",
    mediaUrl: message.media_url || message.mediaUrl || "",
    mimeType: message.mime_type || message.mimeType || "",
    fileName: message.file_name || message.fileName || "",
    at: message.at || message.created_at || new Date().toISOString(),
    status: message.status === "delivered" ? "已送达" : message.status || "已送达",
    optimistic: message.optimistic,
  };
}

function messageTypeForFile(file) {
  if (file.type?.startsWith("image/")) return "image";
  if (file.type?.startsWith("audio/")) return "audio";
  return "file";
}

function normalizeTodo(todo) {
  return {
    id: todo.id,
    title: todo.title,
    dueAt: todo.dueAt || todo.due_time,
    priority: todo.priority || "med",
    notes: todo.notes,
    repeat: todo.repeat || todo.repeat_rule,
    source: todo.source === "steward" ? "agent" : todo.source || "user",
    done: todo.done ?? todo.status === "done",
  };
}

function normalizeMemo(memo) {
  return { id: memo.id, text: memo.text || memo.content || "", at: memo.at || memo.created_at };
}

function normalizeHabit(habit) {
  return {
    id: habit.id,
    name: habit.name,
    remindAt: habit.remindAt,
    schedule: habit.schedule,
    streak: habit.streak || 0,
    last7days: habit.last7days || [0, 0, 0, 0, 0, 0, 0],
  };
}

function normalizeRelation(relation) {
  return {
    id: relation.id || relation.persona_id,
    name: relation.name || `Persona #${relation.persona_id}`,
    role: relation.role || "伙伴",
    avatarHue: relation.avatarHue ?? hueFor(relation.name || String(relation.persona_id)),
    familiarity: relation.familiarity || 0,
  };
}

function normalizeMemoryRecords(records) {
  return {
    facts: (records?.facts || []).map((fact) => ({
      id: fact.id,
      scopeType: fact.scope_type || fact.scopeType || "",
      scopeKey: fact.scope_key || fact.scopeKey || "",
      scopeLabel: fact.scope_label || fact.scopeLabel || fact.scope_key || "",
      subjectType: fact.subject_type || fact.subjectType || "",
      subjectId: fact.subject_id ?? fact.subjectId ?? null,
      predicate: fact.predicate || "fact",
      predicateLabel: fact.predicate_label || fact.predicateLabel || fact.predicate || "事实",
      predicateGroup: fact.predicate_group || fact.predicateGroup || "其他",
      content: fact.content || "",
      sourceMessageId: fact.source_message_id ?? fact.sourceMessageId ?? null,
      confidence: Number(fact.confidence ?? 1),
      supersedesId: fact.supersedes_id ?? fact.supersedesId ?? null,
      superseded: Boolean(fact.superseded ?? fact.superseded),
      createdAt: fact.created_at || fact.createdAt || "",
    })),
    notes: (records?.notes || []).map((note) => ({
      id: note.id,
      personaId: note.persona_id ?? note.personaId,
      personaName: note.persona_name || note.personaName || `Persona #${note.persona_id || note.personaId}`,
      content: note.content || "",
      updatedAt: note.updated_at || note.updatedAt || "",
    })),
  };
}

function normalizeMemoryPredicates(data) {
  return {
    predicates: data?.predicates || {},
    groupOrder: data?.group_order || data?.groupOrder || [],
  };
}

function groupMemoryFacts(facts, groupOrder, predicates) {
  const groups = new Map();
  const orderedGroups = groupOrder.length ? groupOrder : ["其他"];
  orderedGroups.forEach((name) => groups.set(name, []));
  facts.forEach((fact) => {
    const metadata = predicates[fact.predicate] || {};
    const group = fact.predicateGroup || metadata.group || "其他";
    if (!groups.has(group)) {
      groups.set(group, []);
    }
    groups.get(group).push({
      ...fact,
      predicateLabel: fact.predicateLabel || metadata.label || fact.predicate,
    });
  });
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items }));
}

function formatConfidence(value) {
  const numeric = Number.isFinite(Number(value)) ? Number(value) : 0;
  return numeric.toFixed(1);
}

function normalizePersona(persona) {
  const stats = persona.stats || {};
  return {
    id: persona.id,
    name: persona.name || `Persona #${persona.id}`,
    avatarHue: persona.avatarHue ?? hueFor(persona.name || String(persona.id)),
    kind: persona.kind || (persona.is_system ? "系统 · 管家" : `AI · ${persona.model_role || "伙伴"}`),
    personaKind: persona.persona_kind || persona.kind || (persona.is_system ? "system" : "entertainment"),
    creatorUserId: persona.creator_user_id ?? persona.creatorUserId ?? null,
    isAgent: persona.isAgent ?? !persona.is_system,
    is_system: persona.is_system || 0,
    ownerUserId: persona.owner_user_id ?? persona.ownerUserId ?? null,
    model_role: persona.model_role,
    model_override: persona.model_override,
    sim_config: persona.sim_config,
    system_prompt: persona.system_prompt,
    familiarity: Number(persona.familiarity || 0),
    voice: persona.voice || "",
    core: persona.core || persona.persona_core || persona.system_prompt || "",
    style: persona.style || persona.speaking_style || "",
    traits: Array.isArray(persona.traits) ? persona.traits : [],
    channelId: persona.channelId || persona.channel_id || null,
    stats: {
      messages: stats.messages || "0",
      sharedTasks: stats.sharedTasks || "0",
      lastInteraction: stats.lastInteraction || "暂无",
    },
  };
}

function personaOwnerLabel(persona, users = []) {
  if (!persona?.ownerUserId) {
    return `${persona?.name || "AI"}·公共AI`;
  }
  const owner = users.find((user) => Number(user.id) === Number(persona.ownerUserId));
  const ownerName = owner?.display_name || owner?.name || `用户#${persona.ownerUserId}`;
  return `${ownerName}的AI·${persona.name}`;
}

function memberLabel(member) {
  if (member.memberType === "human") {
    return `${member.name}·真人`;
  }
  if (member.ownerUserId) {
    return member.name.includes("的AI·") ? member.name : `${member.name}·私人AI`;
  }
  return `${member.name}·公共AI`;
}

function upsertMessage(current, incoming) {
  const filtered = current.filter(
    (item) => !(item.optimistic && item.fromSelf && item.text === incoming.text),
  );
  if (filtered.some((item) => String(item.id) === String(incoming.id))) {
    return filtered.map((item) => (String(item.id) === String(incoming.id) ? incoming : item));
  }
  return [...filtered, incoming].sort((a, b) => new Date(a.at) - new Date(b.at));
}

function withDateSeparators(messages) {
  let last = "";
  const rows = [];
  for (const message of messages) {
    const key = new Date(message.at).toLocaleDateString("zh-CN");
    if (key !== last) {
      rows.push({ kind: "date", id: `date-${key}`, text: relativeDate(message.at) });
      last = key;
    }
    rows.push({ ...message, kind: "message" });
  }
  return rows;
}

function summarizeTodos(todos) {
  return {
    pending: todos.filter((todo) => !todo.done).length,
    done: todos.filter((todo) => todo.done).length,
    high: todos.filter((todo) => !todo.done && todo.priority === "high").length,
  };
}

function buildSchedule(todos) {
  const dated = todos.filter((todo) => todo.dueAt).slice(0, 5);
  if (!dated.length) {
    return [{ id: "empty", at: new Date().toISOString(), title: "暂无明确时间的日程", state: "todo", tag: null }];
  }
  return dated.map((todo) => ({
    id: todo.id,
    at: safeDateValue(todo.dueAt),
    title: todo.title,
    state: todo.done ? "done" : "todo",
    tag: priorityLabel(todo.priority),
  }));
}

function todoMeta(todo) {
  return `${todo.dueAt || "时间未定"} · ${priorityLabel(todo.priority)} · ${todo.source === "agent" ? "管家添加" : "用户添加"}`;
}

function priorityLabel(priority) {
  return { high: "高优先级", med: "中优先级", low: "低优先级" }[priority] || "中优先级";
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 12) return "早上好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

function initial(value = "") {
  const text = String(value).trim();
  return text ? text.slice(-1) : "C";
}

function hueFor(value = "") {
  let hash = 0;
  for (const char of String(value)) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return hash || 95;
}

function parseLooseDate(value) {
  const fallback = new Date();
  if (!value) return fallback;
  const text = String(value).trim();
  if (!text) return fallback;

  const date = parseLooseDatePart(text) || new Date();
  const time = parseLooseTimePart(text);
  if (time) {
    date.setHours(time.hour, time.minute, 0, 0);
    return date;
  }

  const parsed = new Date(text);
  return isValidDate(parsed) ? parsed : date;
}

function safeDateValue(value) {
  const parsed = parseLooseDate(value);
  return isValidDate(parsed) ? parsed.toISOString() : new Date().toISOString();
}

function formatShortTime(value) {
  if (!value) return "";
  const text = String(value).trim();
  if (!/^\d{4}-\d{2}-\d{2}/.test(text) && !/(\d{1,2}):(\d{2})/.test(text) && !/[早上上午中午下午晚上今晚明早明天后天今天昨天前天].*点/.test(text)) {
    return text;
  }
  const date = parseLooseDate(value);
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function parseLooseDatePart(text) {
  const exact = text.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (exact) {
    const date = new Date(Number(exact[1]), Number(exact[2]) - 1, Number(exact[3]));
    return isValidDate(date) ? date : null;
  }

  const date = new Date();
  if (/后天/.test(text)) date.setDate(date.getDate() + 2);
  else if (/明天|明早/.test(text)) date.setDate(date.getDate() + 1);
  else if (/昨天/.test(text)) date.setDate(date.getDate() - 1);
  else if (/前天/.test(text)) date.setDate(date.getDate() - 2);
  return date;
}

function parseLooseTimePart(text) {
  const colon = text.match(/(\d{1,2}):(\d{2})/);
  if (colon) {
    return normalizeLooseHour(Number(colon[1]), Number(colon[2]), text);
  }

  const cnHour = text.match(/([零〇一二两三四五六七八九十\d]{1,3})点(?:([零〇一二两三四五六七八九十\d]{1,3})分?)?/);
  if (cnHour) {
    return normalizeLooseHour(chineseNumber(cnHour[1]), cnHour[2] ? chineseNumber(cnHour[2]) : 0, text);
  }

  return null;
}

function normalizeLooseHour(hour, minute, text) {
  if (!Number.isFinite(hour) || !Number.isFinite(minute) || minute < 0 || minute > 59) return null;
  let nextHour = hour;
  if (/下午|晚上|今晚/.test(text) && nextHour >= 1 && nextHour < 12) nextHour += 12;
  if (/中午/.test(text) && nextHour >= 1 && nextHour < 11) nextHour += 12;
  if (/凌晨|早上|上午|明早/.test(text) && nextHour === 12) nextHour = 0;
  if (nextHour < 0 || nextHour > 23) return null;
  return { hour: nextHour, minute };
}

function chineseNumber(value) {
  if (/^\d+$/.test(value)) return Number(value);
  const digits = { 零: 0, "〇": 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  if (value === "十") return 10;
  const tenIndex = value.indexOf("十");
  if (tenIndex >= 0) {
    const left = value.slice(0, tenIndex);
    const right = value.slice(tenIndex + 1);
    return (left ? digits[left] : 1) * 10 + (right ? digits[right] : 0);
  }
  return digits[value] ?? Number.NaN;
}

function isValidDate(date) {
  return date instanceof Date && !Number.isNaN(date.getTime());
}

function formatHour(value) {
  return formatShortTime(value) || "--:--";
}

function relativeDate(value) {
  const date = parseLooseDate(value);
  const today = new Date().toLocaleDateString("zh-CN");
  const target = date.toLocaleDateString("zh-CN");
  return target === today ? "今天" : target;
}

createRoot(document.getElementById("root")).render(<App />);
