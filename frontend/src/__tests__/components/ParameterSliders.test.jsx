/**
 * Tests for ParameterSliders Component
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ParameterSliders from '../../components/generation/ParameterSliders';

describe('ParameterSliders', () => {
  const mockOnStepsChange = vi.fn();
  const mockOnGuidanceChange = vi.fn();

  beforeEach(() => {
    mockOnStepsChange.mockClear();
    mockOnGuidanceChange.mockClear();
  });

  it('renders both sliders with labels', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    expect(screen.getByText('Sampling Steps')).toBeInTheDocument();
    expect(screen.getByText('Guidance Scale')).toBeInTheDocument();
  });

  it('displays current steps value', () => {
    render(
      <ParameterSliders
        steps={35}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    expect(screen.getByText('35')).toBeInTheDocument();
  });

  it('displays current guidance value with decimal', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={7.5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    expect(screen.getByText('7.5')).toBeInTheDocument();
  });

  it('calls onStepsChange when steps slider is moved', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    const stepsSlider = screen.getByLabelText('Sampling steps');
    fireEvent.change(stepsSlider, { target: { value: '40' } });

    expect(mockOnStepsChange).toHaveBeenCalledWith(40);
  });

  it('calls onGuidanceChange when guidance slider is moved', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    const guidanceSlider = screen.getByLabelText('Guidance scale');
    fireEvent.change(guidanceSlider, { target: { value: '8.0' } });

    expect(mockOnGuidanceChange).toHaveBeenCalled();
  });

  it('rounds guidance value to nearest 0.5', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    const guidanceSlider = screen.getByLabelText('Guidance scale');

    // Test rounding 7.3 -> 7.5
    fireEvent.change(guidanceSlider, { target: { value: '7.3' } });
    expect(mockOnGuidanceChange).toHaveBeenCalledWith(7.5);

    // Test rounding 7.8 -> 8.0 (Math.round(15.6) / 2 = 16 / 2 = 8.0)
    fireEvent.change(guidanceSlider, { target: { value: '7.8' } });
    expect(mockOnGuidanceChange).toHaveBeenCalledWith(8);
  });

  it('shows min/max markers for steps slider', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    // Steps slider markers: 3, 28, 50
    const markers = screen.getAllByText('3');
    expect(markers.length).toBeGreaterThan(0);
    expect(screen.getAllByText('50').length).toBeGreaterThan(0);
  });

  it('shows min/max markers for guidance slider', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    // Guidance slider markers: 0, 5, 10
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
  });

  it('shows description text for both sliders', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    expect(screen.getByText(/Higher values = more refined images/i)).toBeInTheDocument();
    expect(screen.getByText(/Higher values = closer adherence to prompt/i)).toBeInTheDocument();
  });

  it('disables sliders when disabled prop is true', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
        disabled={true}
      />
    );

    const stepsSlider = screen.getByLabelText('Sampling steps');
    const guidanceSlider = screen.getByLabelText('Guidance scale');

    expect(stepsSlider).toBeDisabled();
    expect(guidanceSlider).toBeDisabled();
  });

  it('allows sliders when disabled prop is false', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
        disabled={false}
      />
    );

    const stepsSlider = screen.getByLabelText('Sampling steps');
    const guidanceSlider = screen.getByLabelText('Guidance scale');

    expect(stepsSlider).not.toBeDisabled();
    expect(guidanceSlider).not.toBeDisabled();
  });

  it('has correct range attributes for steps slider', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    const stepsSlider = screen.getByLabelText('Sampling steps');
    expect(stepsSlider).toHaveAttribute('min', '3');
    expect(stepsSlider).toHaveAttribute('max', '50');
    expect(stepsSlider).toHaveAttribute('step', '1');
  });

  it('has correct range attributes for guidance slider', () => {
    render(
      <ParameterSliders
        steps={28}
        guidance={5}
        onStepsChange={mockOnStepsChange}
        onGuidanceChange={mockOnGuidanceChange}
      />
    );

    const guidanceSlider = screen.getByLabelText('Guidance scale');
    expect(guidanceSlider).toHaveAttribute('min', '0');
    expect(guidanceSlider).toHaveAttribute('max', '10');
    expect(guidanceSlider).toHaveAttribute('step', '0.5');
  });
});
