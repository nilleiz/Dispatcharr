import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SystemSettingsForm from '../SystemSettingsForm';

vi.mock('../../../../store/settings.jsx', () => ({ default: vi.fn() }));
vi.mock('../../../../constants.js', () => ({ REGION_CHOICES: [] }));
vi.mock('../../../../hooks/useSettingsSaveGuard.jsx', () => ({
  default: () => ({
    isSavingRef: { current: false },
    runSave: (callback) => callback(),
  }),
}));
vi.mock('../../../../utils/pages/SettingsUtils.js', () => ({
  getChangedGroupSettings: vi.fn(),
  parseGroupSettings: vi.fn(),
  saveGroupSettings: vi.fn(),
}));
vi.mock('../../../../utils/forms/settings/SystemSettingsFormUtils.js', () => ({
  getSystemSettingsFormInitialValues: vi.fn(() => ({})),
}));
vi.mock('../ConnectionSecurityPanel.jsx', () => ({ default: () => null }));
vi.mock('@mantine/form', () => ({ useForm: vi.fn() }));
vi.mock('@mantine/core', () => ({
  Alert: ({ title }) => <div>{title}</div>,
  Button: ({ children, onClick }) => (
    <button onClick={onClick}>{children}</button>
  ),
  Divider: () => <hr />,
  Flex: ({ children }) => <div>{children}</div>,
  NumberInput: ({ label }) => <div>{label}</div>,
  Select: ({ label }) => <div>{label}</div>,
  Stack: ({ children }) => <div>{children}</div>,
  Switch: ({ id, label, description }) => (
    <label htmlFor={id}>
      {label}
      <span>{description}</span>
      <input id={id} data-testid={id} type="checkbox" />
    </label>
  ),
}));

import { useForm } from '@mantine/form';
import useSettingsStore from '../../../../store/settings.jsx';
import {
  getChangedGroupSettings,
  parseGroupSettings,
  saveGroupSettings,
} from '../../../../utils/pages/SettingsUtils.js';

const settings = {
  system_settings: { value: { max_system_events: 100 } },
  epg_settings: { value: { date_episode_compatibility: true } },
};

describe('SystemSettingsForm date episode compatibility', () => {
  let form;

  beforeEach(() => {
    vi.clearAllMocks();
    form = {
      values: {
        max_system_events: 100,
        date_episode_compatibility: true,
      },
      getValues: vi.fn(() => form.values),
      setValues: vi.fn(),
      setFieldValue: vi.fn(),
      getInputProps: vi.fn(() => ({})),
      onSubmit: vi.fn((callback) => callback),
      submitting: false,
    };
    vi.mocked(useForm).mockReturnValue(form);
    vi.mocked(useSettingsStore).mockImplementation((selector) =>
      selector({
        settings,
        environment: { env_mode: 'aio', ip_lookup_env_disabled: false },
      })
    );
    vi.mocked(useSettingsStore).getState = vi.fn(() => ({ settings }));
    vi.mocked(parseGroupSettings).mockImplementation((_settings, group) =>
      group === 'epg_settings'
        ? { date_episode_compatibility: true }
        : { max_system_events: 100 }
    );
    vi.mocked(getChangedGroupSettings).mockImplementation(
      (_values, _settings, group) =>
        group === 'epg_settings' ? { date_episode_compatibility: true } : {}
    );
    vi.mocked(saveGroupSettings).mockResolvedValue(undefined);
  });

  it('renders the global compatibility switch', () => {
    render(<SystemSettingsForm active={true} />);

    expect(
      screen.getByText('Use Air Date for Unnumbered Episodes')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('date_episode_compatibility')
    ).toBeInTheDocument();
  });

  it('hydrates the form from system and epg settings', () => {
    render(<SystemSettingsForm active={true} />);

    expect(parseGroupSettings).toHaveBeenCalledWith(
      settings,
      'system_settings'
    );
    expect(parseGroupSettings).toHaveBeenCalledWith(settings, 'epg_settings');
    expect(form.setValues).toHaveBeenCalledWith({
      max_system_events: 100,
      date_episode_compatibility: true,
    });
  });

  it('saves the global option in epg settings without changing an output URL', async () => {
    render(<SystemSettingsForm active={true} />);

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(getChangedGroupSettings).toHaveBeenCalledWith(
        form.values,
        settings,
        'epg_settings'
      );
      expect(saveGroupSettings).toHaveBeenCalledWith(settings, 'epg_settings', {
        date_episode_compatibility: true,
      });
    });
  });
});
