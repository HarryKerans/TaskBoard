import type { ReactElement } from 'react';

type Priority = 'high' | 'medium' | 'low';

// Deterministic colour from tag name — same tag always gets same colour
const TAG_COLOURS = [
  { bg: '#e8f0fe', color: '#1a56db' },
  { bg: '#fce8f3', color: '#9b1c5e' },
  { bg: '#def7ec', color: '#046c4e' },
  { bg: '#fef3c7', color: '#92400e' },
  { bg: '#ede9fe', color: '#5b21b6' },
  { bg: '#fce4ec', color: '#b71c1c' },
  { bg: '#e0f2f1', color: '#004d40' },
  { bg: '#fff3e0', color: '#e65100' },
];

function getTagColour(name: string): { bg: string; color: string } {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return TAG_COLOURS[Math.abs(hash) % TAG_COLOURS.length];
}

type TaskCardProps = {
  id: string;
  title: string;
  priority: Priority;
  tags: string[];
  selected: boolean;
  onToggle: (id: string) => void;
  onEdit?: () => void;
};

function TaskCard({ id, title, priority, tags, selected, onToggle, onEdit }: TaskCardProps): ReactElement {
  return (
    <label className={`task-card${selected ? ' task-card--selected' : ''}`} htmlFor={`task-cb-${id}`}>
      {onEdit && (
        <button
          className="task-card__edit"
          aria-label="Edit task"
          onClick={e => { e.preventDefault(); e.stopPropagation(); onEdit(); }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
          </svg>
        </button>
      )}
      <input
        className="task-card__checkbox"
        type="checkbox"
        id={`task-cb-${id}`}
        checked={selected}
        onChange={() => onToggle(id)}
      />
      <div className="task-card__body">
        <div>
          <p className="task-card__label">Task</p>
          <h2 className="task-card__title">{title}</h2>
          {tags.length > 0 && (
            <div className="task-card__tags">
              {tags.map(tag => {
                const { bg, color } = getTagColour(tag);
                return (
                  <span key={tag} className="task-card__tag" style={{ background: bg, color }}>
                    {tag}
                  </span>
                );
              })}
            </div>
          )}
        </div>
        <div className="task-card__meta">
          <span className="task-card__meta-label">Priority</span>
          <span className={`task-card__priority task-card__priority--${priority}`}>
            {priority}
          </span>
        </div>
      </div>
    </label>
  );
}

export default TaskCard;
