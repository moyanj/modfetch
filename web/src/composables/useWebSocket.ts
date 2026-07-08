import { ref, onUnmounted } from 'vue';
import type { WsEvent } from '@/types/events';

type WsStatus = 'connecting' | 'open' | 'closed' | 'error';

export function useWebSocket() {
  const events = ref<WsEvent[]>([]);
  const status = ref<WsStatus>('closed');
  const lastEvent = ref<WsEvent | null>(null);

  let ws: WebSocket | null = null;
  let currentUrl: string | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function connect(url: string) {
    if (ws && currentUrl === url) return;
    disconnect();

    status.value = 'connecting';
    currentUrl = url;
    const socket = new WebSocket(url);
    ws = socket;

    socket.onopen = () => {
      if (ws !== socket) return;
      status.value = 'open';
    };

    socket.onmessage = (message) => {
      if (ws !== socket) return;
      try {
        const event = JSON.parse(message.data) as WsEvent;
        events.value.push(event);
        lastEvent.value = event;
      } catch {
        // ignore invalid json
      }
    };

    socket.onclose = () => {
      if (ws !== socket) return;
      status.value = 'closed';
      ws = null;
      currentUrl = null;
    };

    socket.onerror = () => {
      if (ws !== socket) return;
      status.value = 'error';
    };
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      const socket = ws;
      ws = null;
      socket.close();
    }
    currentUrl = null;
    status.value = 'closed';
  }

  onUnmounted(() => {
    disconnect();
  });

  return {
    events,
    status,
    lastEvent,
    connect,
    disconnect,
  };
}
