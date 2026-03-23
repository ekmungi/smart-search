// Reusable empty state with icon, heading, description, and optional action.

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: LucideIcon;
  heading: string;
  description?: string;
  action?: ReactNode;
}

/** Centered empty state placeholder for views with no data. */
export default function EmptyState({
  icon: Icon,
  heading,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Icon size={48} className="text-text-muted opacity-40 mb-4" />
      <h3 className="text-sm font-medium text-text-secondary mb-1">
        {heading}
      </h3>
      {description && (
        <p className="text-xs text-text-muted max-w-xs mb-4">{description}</p>
      )}
      {action}
    </div>
  );
}
