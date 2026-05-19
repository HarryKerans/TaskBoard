import type { ReactElement } from 'react';

type Priority = 'high' | 'medium' | 'low';

type TaskCardProps = {
  id: string;
  title: string;
  priority: Priority;
  selected: boolean;
  onToggle: (id: string) => void;
};

function TaskCard({ id, title, priority, selected, onToggle }: TaskCardProps): ReactElement {
  return (
    <label className={`task-card${selected ? ' task-card--selected' : ''}`} htmlFor={`task-cb-${id}`}>
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
