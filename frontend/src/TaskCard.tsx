import type { ReactElement } from 'react';

type Priority = 'high' | 'medium' | 'low';

type TaskCardProps = {
  title: string;
  priority: Priority;
};

function TaskCard({ title, priority }: TaskCardProps): ReactElement {
  return (
    <article className="task-card">
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
    </article>
  );
}

export default TaskCard;
