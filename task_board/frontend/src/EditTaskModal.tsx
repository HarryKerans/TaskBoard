import { useState, useEffect, type ReactElement } from 'react';
import type { LocalTask, Priority } from './alexaApi';

type EditTaskModalProps = {
  task: LocalTask;
  onSave: (updates: { title: string; description: string; priority: Priority }) => Promise<void>;
  onClose: () => void;
};

function EditTaskModal({ task, onSave, onClose }: EditTaskModalProps): ReactElement {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description ?? '');
  const [priority, setPriority] = useState<Priority>(task.priority);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await onSave({ title, description, priority });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2 className="modal__title">Edit Task</h2>
        {error && <p className="error">{error}</p>}
        <div className="form">
          <label className="form__label">
            Title
            <input
              className="form__input"
              value={title}
              onChange={e => setTitle(e.target.value)}
            />
          </label>
          <label className="form__label">
            Description
            <textarea
              className="form__input form__textarea"
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={3}
            />
          </label>
          <label className="form__label">
            Priority
            <select
              className="form__input"
              value={priority}
              onChange={e => setPriority(e.target.value as Priority)}
            >
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </label>
        </div>
        <div className="modal__actions">
          <button className="btn" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button className="btn btn--secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export default EditTaskModal;
