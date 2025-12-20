import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="min-h-screen bg-[#0D0E12] text-white overflow-hidden selection:bg-[#00e599]/30">
      {/* Neon Grid Background */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        <div className="absolute top-0 left-0 right-0 h-[500px] bg-[radial-gradient(circle_800px_at_50%_-100px,#00e59915,transparent)]"></div>
      </div>

      {/* Navbar Placeholder */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/5 bg-[#0D0E12]/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2 font-bold text-xl tracking-tighter">
            <div className="w-8 h-8 bg-[#00e599] rounded-lg flex items-center justify-center text-black">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M3 7V5C3 4.44772 3.44772 4 4 4H20C20.5523 4 21 4.44772 21 5V7M3 7V19C3 19.5523 3.44772 20 4 20H20C20.5523 20 21 19.5523 21 19V7M3 7H21M12 11V15M9 13H15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            RELIX
          </div>
          <div className="hidden md:flex gap-6 text-sm font-medium text-zinc-400">
            <span className="hover:text-white cursor-pointer transition-colors">Features</span>
            <span className="hover:text-white cursor-pointer transition-colors">Pricing</span>
            <span className="hover:text-white cursor-pointer transition-colors">Docs</span>
          </div>
          <div className="flex gap-4">
            <a href="/" className="text-sm font-medium text-zinc-300 hover:text-white pt-2">Home</a>
          </div>
        </div>
      </nav>

      <div className="flex items-center justify-center min-h-screen pt-16">
        <SignUp />
      </div>
    </div>
  );
}