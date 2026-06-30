import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'serve-fake-data',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && req.url.startsWith('/fake-data/')) {
            // Remove prefix and query params
            const relativePath = decodeURIComponent(req.url.slice('/fake-data/'.length).split('?')[0]);
            const filePath = path.join(__dirname, '../fake-data', relativePath);
            
            if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
              res.setHeader('Content-Type', getMimeType(filePath));
              res.setHeader('Access-Control-Allow-Origin', '*');
              res.end(fs.readFileSync(filePath));
              return;
            }
          }
          next();
        });
      }
    }
  ],
})

function getMimeType(filePath: string) {
  if (filePath.endsWith('.json')) return 'application/json';
  if (filePath.endsWith('.log')) return 'text/plain';
  if (filePath.endsWith('.js')) return 'application/javascript';
  if (filePath.endsWith('.css')) return 'text/css';
  return 'application/octet-stream';
}
