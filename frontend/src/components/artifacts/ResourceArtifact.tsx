import type { ResourceListContent } from "../../services/api";

interface Props {
  content: ResourceListContent;
}

export function ResourceArtifact({ content }: Props) {
  // Group by category if categories exist
  const categories = new Map<string, typeof content.resources>();
  for (const r of content.resources) {
    const cat = r.category || "Resources";
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(r);
  }

  return (
    <div className="resource-artifact">
      {[...categories.entries()].map(([cat, resources]) => (
        <div key={cat} className="resource-category">
          {categories.size > 1 && (
            <div className="resource-category-name">{cat}</div>
          )}
          {resources.map((r, i) => (
            <a
              key={i}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="resource-item"
            >
              <div className="resource-title">{r.title}</div>
              <div className="resource-desc">{r.description}</div>
              <div className="resource-url">{(() => { try { return new URL(r.url).hostname; } catch { return r.url; } })()}</div>
            </a>
          ))}
        </div>
      ))}
    </div>
  );
}
