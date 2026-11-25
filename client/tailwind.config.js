/** @type {import('tailwindcss').Config} */
export default { content: ['./index.html', './src/**/*.{js,jsx}'], theme: { extend: { colors: { goal: { background: '#0E0F13', card: '#17181D', border: '#26272E', text: '#F5F5F7', muted: '#A8AAB5', lime: '#C6F432', live: '#FF4D4D' } }, fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] }, borderRadius: { card: '16px' } } }, plugins: [] };
