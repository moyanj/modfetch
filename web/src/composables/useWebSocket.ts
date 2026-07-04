import { ref, onUnmounted } from 'vue';
import type { WsEvent } from '@/types/events';

type WsStatus = 'connecting' | 'open' | 'closed' | 'error';

export function useWebSocket() {
  const events = ref<WsEvent[]>([]);
  const status = ref<WsStatus>('closed');
  const lastEvent = ref<WsEvent | null>(null);

  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function connect(url: string) {
    if (ws) return;

    status.value = 'connecting';
    ws = new WebSocket(url);

    ws.onopen = () => {
      status.value = 'open';
    };

    ws.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as WsEvent;
        events.value.push(event);
        lastEvent.value = event;
      } catch {
        // ignore invalid json
      }
    };

    ws.onclose = () => {
      status.value = 'closed';
      ws = null;
    };

    ws.onerror = () => {
      status.value = 'error';
    };
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
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
