
# RELIX Frontend (Next.js)

## ✨ New Features

- Universal Light/Dark theme toggle (next-themes, Tailwind)
- ThemeProvider and ThemeToggle components
- Toggle available on all pages (landing, dashboard, chat, upload, sign-in, sign-up)
- All colors now use theme-aware CSS variables for accessibility

## Getting Started

```bash
npm install
npm run dev
# http://localhost:3000
```

## Environment

Create `.env.local` with:
```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Contributing

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes
3. Submit PR

---

**Built with ❤️ using Next.js, Tailwind, and next-themes**
