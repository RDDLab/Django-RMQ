import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const currentSidebar = [
  'intro',
  'getting-started',
  'configuration',
  'producers',
  'consumers',
  'topology',
  'registries',
  'management-commands',
  'reliability',
  'multiple-connections',
  'clusters',
  'testing',
  'api-reference',
  'contrib',
];

const sidebars: SidebarsConfig = {
  docs: currentSidebar,
};

export default sidebars;
