"use client";

import Link from "next/link";
import { UploadCloud, LayoutDashboard, Search, Home } from "lucide-react";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const Navbar = () => {
    const pathname = usePathname();

    const navItems = [
        { name: "Home", href: "/", icon: Home },
        { name: "Upload Bill", href: "/upload", icon: UploadCloud },
        { name: "Hospital Search", href: "/hospitals", icon: Search },
        { name: "Analytics", href: "/analytics", icon: LayoutDashboard },
    ];

    return (
        <nav className="fixed w-full z-50 top-0 start-0 bg-white/90 backdrop-blur-sm border-b border-slate-200 shadow-sm transition-all">
            <div className="container mx-auto px-4 h-16 flex items-center justify-between">
                <Link href="/" className="flex items-center gap-2 group">
                    <div className="bg-teal-600 w-8 h-8 rounded-lg flex items-center justify-center shadow-sm group-hover:bg-teal-700 transition-colors">
                        <span className="text-white font-bold text-lg">M</span>
                    </div>
                    <span className="font-bold text-xl tracking-tight text-slate-800">
                        Medicon
                    </span>
                </Link>

                <div className="flex items-center gap-1">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    "px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 flex items-center gap-2 relative group",
                                    isActive
                                        ? "text-teal-700 bg-teal-50 font-semibold"
                                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                                )}
                            >
                                <item.icon className={cn("w-4 h-4", isActive && "text-teal-600")} />
                                <span className="hidden md:block">{item.name}</span>
                            </Link>
                        );
                    })}
                </div>
            </div>
        </nav>
    );
};

export default Navbar;
