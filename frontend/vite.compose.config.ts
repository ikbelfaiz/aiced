import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Compiled assets only. All API routing belongs to the gateway.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: '0.0.0.0', port: 5173, strictPort: true, allowedHosts: ['frontend', 'gateway'] },
  preview: { host: '0.0.0.0', port: 5173, strictPort: true, allowedHosts: ['frontend', 'gateway'] },
});
