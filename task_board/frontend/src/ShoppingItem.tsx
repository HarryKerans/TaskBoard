import type { ReactElement } from 'react';

type ShoppingItemProps = {
  id: string;
  title: string;
  selected: boolean;
  onToggle: (id: string) => void;
};

function ShoppingItem({ id, title, selected, onToggle }: ShoppingItemProps): ReactElement {
  return (
    <label className={`shopping-item${selected ? ' shopping-item--selected' : ''}`} htmlFor={`shop-cb-${id}`}>
      <input
        className="shopping-item__checkbox"
        type="checkbox"
        id={`shop-cb-${id}`}
        checked={selected}
        onChange={() => onToggle(id)}
      />
      <span className="shopping-item__title">{title}</span>
    </label>
  );
}

export default ShoppingItem;
