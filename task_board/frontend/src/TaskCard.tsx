import type { ReactElement } from 'react';

type Priority = 'high' | 'medium' | 'low';

type TaskCardProps = {
  id: string;
  title: string;
  priority: Priority;
  selected: boolean;
  onToggle: (id: string) => void;
  onEdit?: () => void;
};

function TaskCard({ id, title, priority, selected, onToggle, onEdit }: TaskCardProps): ReactElement {
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
