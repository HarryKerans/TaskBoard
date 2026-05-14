import { render, screen } from '@testing-library/react';
import App from './App';

test('renders task card', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /make task dashboard/i })).toBeInTheDocument();
  expect(screen.getByText(/high/i)).toBeInTheDocument();
});
