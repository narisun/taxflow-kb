import { NextResponse } from "next/server";

interface IrsNewsItem {
  id: number;
  title: string;
  date: string;
  url: string;
  category: string;
}

let cache: { items: IrsNewsItem[]; fetchedAt: number } | null = null;
const CACHE_TTL = 15 * 60 * 1000; // 15 minutes

function categorize(title: string): string {
  const t = title.toLowerCase();
  if (t.includes("refund") || t.includes("payment")) return "Refunds";
  if (t.includes("deadline") || t.includes("extension") || t.includes("file")) return "Deadlines";
  if (t.includes("scam") || t.includes("phish") || t.includes("fraud") || t.includes("whistleblower")) return "Security";
  if (t.includes("regulation") || t.includes("compliance") || t.includes("guidance")) return "Compliance";
  if (t.includes("e-file") || t.includes("online") || t.includes("digital") || t.includes("tool")) return "E-File";
  if (t.includes("tip") || t.includes("resource") || t.includes("help")) return "Resources";
  if (t.includes("tax account") || t.includes("business")) return "Business";
  return "News";
}

export async function GET() {
  if (cache && Date.now() - cache.fetchedAt < CACHE_TTL) {
    return NextResponse.json(cache.items);
  }

  try {
    const res = await fetch("https://www.irs.gov/newsroom", {
      headers: { "User-Agent": "TaxFlowAI/1.0 (CPA Platform)" },
      next: { revalidate: 900 },
    });

    if (!res.ok) throw new Error(`IRS returned ${res.status}`);

    const html = await res.text();

    // Parse news items from the newsroom HTML
    // IRS newsroom lists items as links with dates in a structured list
    const items: IrsNewsItem[] = [];
    const pattern = /<a[^>]+href="(\/newsroom\/[^"]+)"[^>]*>([^<]+)<\/a>/gi;
    const datePattern = /(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}/gi;

    // Extract all newsroom links and nearby dates
    const sections = html.split(/<li[^>]*>/i);
    let id = 1;
    for (const section of sections) {
      if (items.length >= 10) break;
      const linkMatch = section.match(/<a[^>]+href="(\/newsroom\/[^"]+)"[^>]*>([^<]+)<\/a>/i);
      if (!linkMatch) continue;

      const url = linkMatch[1];
      const title = linkMatch[2].trim();

      // Skip navigation/utility links
      if (title.length < 20 || url.includes("rss") || url.includes("subscription")) continue;

      const dateMatch = section.match(/(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}/i);
      const rawDate = dateMatch ? dateMatch[0] : "";
      const shortDate = rawDate
        ? new Date(rawDate).toLocaleDateString("en-US", { month: "short", day: "numeric" })
        : "";

      items.push({
        id: id++,
        title,
        date: shortDate,
        url: `https://www.irs.gov${url}`,
        category: categorize(title),
      });
    }

    if (items.length > 0) {
      cache = { items, fetchedAt: Date.now() };
    } else if (cache) {
      // HTML structure may have changed — serve stale cache rather than empty
      console.warn("[irs-news] Parsed 0 items from IRS newsroom — HTML structure may have changed. Serving stale cache.");
      return NextResponse.json(cache.items);
    }

    return NextResponse.json(items);
  } catch (err) {
    // Return cached data if available, even if stale
    console.error("[irs-news] Failed to fetch IRS newsroom:", err);
    if (cache) return NextResponse.json(cache.items);
    return NextResponse.json([], { status: 502 });
  }
}
