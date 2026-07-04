const typeColors: Record<string, { bg: string; border: string; text: string }> = {
  mod: { bg: 'rgba(124, 179, 66, 0.2)', border: 'rgba(124, 179, 66, 0.6)', text: '#8BC34A' },
  resourcepack: { bg: 'rgba(77, 208, 225, 0.2)', border: 'rgba(77, 208, 225, 0.6)', text: '#4DD0E1' },
  shader: { bg: 'rgba(255, 215, 0, 0.2)', border: 'rgba(255, 215, 0, 0.6)', text: '#FFD700' },
  forge: { bg: 'rgba(255, 152, 0, 0.2)', border: 'rgba(255, 152, 0, 0.6)', text: '#FF9800' },
  neoforge: { bg: 'rgba(255, 152, 0, 0.2)', border: 'rgba(255, 152, 0, 0.6)', text: '#FF9800' },
  fabric: { bg: 'rgba(124, 179, 66, 0.2)', border: 'rgba(124, 179, 66, 0.6)', text: '#8BC34A' },
  quilt: { bg: 'rgba(63, 81, 181, 0.2)', border: 'rgba(63, 81, 181, 0.6)', text: '#3F51B5' },
  success: { bg: 'rgba(124, 179, 66, 0.2)', border: 'rgba(124, 179, 66, 0.6)', text: '#8BC34A' },
  warning: { bg: 'rgba(255, 152, 0, 0.2)', border: 'rgba(255, 152, 0, 0.6)', text: '#FF9800' },
  error: { bg: 'rgba(255, 82, 82, 0.2)', border: 'rgba(255, 82, 82, 0.6)', text: '#FF5252' },
  datapack: { bg: 'rgba(156, 39, 176, 0.2)', border: 'rgba(156, 39, 176, 0.6)', text: '#9C27B0' },
};

export function useModTypes() {
  const getTypeColor = (type: string) => {
    return typeColors[type] || { bg: 'rgba(125, 125, 125, 0.2)', border: 'rgba(125, 125, 125, 0.6)', text: '#7D7D7D' };
  };

  const getTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      mod: 'MOD',
      resourcepack: '资源包',
      shader: '光影',
      datapack: '数据包',
      forge: 'Forge',
      neoforge: 'NeoForge',
      fabric: 'Fabric',
      quilt: 'Quilt',
      file: '文件',
    };
    return labels[type] || type.toUpperCase();
  };

  return {
    getTypeColor,
    getTypeLabel,
    typeColors,
  };
}
