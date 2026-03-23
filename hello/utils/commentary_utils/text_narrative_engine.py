from hello.utils.commentary_utils.utils import format_metric_value
from dataclasses import dataclass
from typing import Any
import os, yaml
from hello.ml.logger import GLOBAL_LOGGER as logger

@dataclass
class TemplateContext:
    """Context information for template selection and variable substitution."""
    property_type: str  # "all", "office", "industrial"
    office_class: str | None = None  # "class_a", "class_b" for office properties
    current_quarter: str = ""
    market_name: str = ""
    number_of_years: int = 5


class TemplateLoader:
    """Handles loading and caching of YAML templates, supporting local files, Snowflake stage, and package resources."""

    def __init__(self, template_path: str):
        """
        Initialize the template loader.
        Args:
            template_path: Path to the YAML template file or Snowflake stage.
        """

        self.template_path = template_path
        self._template_cache = None

    def load_template(self) -> dict[str, Any]:
        """
        Load the YAML template file from a local path or Snowflake stage.
        Returns:
            dict: The loaded template structure
        """
        if self._template_cache is None:
            try:
                yaml_path = self.template_path
                if os.path.isabs(yaml_path) and os.path.exists(yaml_path):
                    with open(yaml_path, 'r', encoding='utf-8') as f:
                        self._template_cache = yaml.load(f, Loader=yaml.FullLoader)
                    logger.debug(f"Loaded template from absolute path: {yaml_path}")
                elif os.path.exists(yaml_path):
                    with open(yaml_path, 'r', encoding='utf-8') as f:
                        self._template_cache = yaml.load(f, Loader=yaml.FullLoader)
                    logger.debug(f"Loaded template from relative path: {yaml_path}")
                else:
                    logger.error(f"Template file not found: {yaml_path}")
                    raise FileNotFoundError(f"Template file not found: {yaml_path}")
            except Exception as e:
                logger.error(f"Error loading template from '{self.template_path}': {e}")
                raise
        return self._template_cache

    def reload_template(self) -> dict[str, Any]:
        """Force reload of the template file."""
        self._template_cache = None
        return self.load_template()


class TextSelector:
    """Handles template selection with property type/class fallback logic."""
    
    @staticmethod
    def select_text(
        template_section: dict[str, Any], 
        context: TemplateContext, 
        direction: str
    ) -> str:
        """
        Select the appropriate text template with fallback logic.
        
        The selection priority is:
        1. Property type + office class + direction (for office properties with class)
        2. Property type + direction
        3. "all" + direction
        4. Empty string if no match found
        
        Args:
            template_section: The template section (e.g., core_text, qoq_text)
            context: Template context with property type and class info
            direction: Direction indicator ("up", "down", "neutral", "none")
            
        Returns:
            str: Selected template text or empty string
        """
        if not template_section:
            logger.debug("Empty template section")
            return ""
            
        # Normalize property type to lowercase for comparison
        property_type_lower = context.property_type.lower() if context.property_type else ""
        
        # Priority 1: Property type + office class + direction (only when office_class is explicitly set)
        if (property_type_lower == "office" and 
            context.office_class and 
            property_type_lower in template_section):
            
            property_section = template_section[property_type_lower]
            if isinstance(property_section, dict) and context.office_class in property_section:
                class_section = property_section[context.office_class]
                if isinstance(class_section, dict) and direction in class_section:
                    class_text = class_section[direction]
                    if class_text:
                        logger.debug(f"Selected {property_type_lower}.{context.office_class}.{direction} template")
                        return class_text
        
        # Priority 2: Property type + direction (for office without class and other property types)
        if property_type_lower in template_section:
            property_section = template_section[property_type_lower]
            if isinstance(property_section, dict) and direction in property_section:
                # Make sure we're getting the direct property-level text, not nested class text
                property_text = property_section.get(direction)
                if property_text and isinstance(property_text, str):  # Ensure it's a string, not a dict
                    logger.debug(f"Selected {property_type_lower}.{direction} template")
                    return property_text
        
        # Priority 3: "all" + direction (fallback)
        if "all" in template_section:
            all_section = template_section["all"]
            if isinstance(all_section, dict) and direction in all_section:
                all_text = all_section[direction]
                if all_text:
                    logger.debug(f"Selected all.{direction} template (fallback)")
                    return all_text
        
        # No match found
        logger.warning(f"No template found for property_type='{context.property_type}', office_class='{context.office_class}', direction='{direction}'")
        return ""


class VariableSubstituter:
    """Handles variable substitution in template text."""
    
    @staticmethod
    def substitute_variables(
        template_text: str, 
        metrics_data: dict[str, Any], 
        context: TemplateContext
    ) -> str:
        """
        Substitute variables in template text with actual values.
        
        Variables in template text are enclosed in square brackets, e.g., [current_quarter]
        
        Args:
            template_text: Template text with variables to substitute
            metrics_data: Metrics data dictionary containing calculated values
            context: Template context with additional values
            
        Returns:
            str: Text with variables substituted
        """

        if not template_text:
            return ""
            
        def _format_quarter_for_display(quarter_str: str) -> str:
            """Convert quarter format from 'YYYY QQ' to 'QQ YYYY' for display."""
            if not quarter_str or ' ' not in quarter_str:
                return quarter_str
            
            try:
                parts = quarter_str.split(' ')
                if len(parts) == 2:
                    year = parts[0]
                    quarter = parts[1]
                    return f"{quarter} {year}"
                return quarter_str
            except (IndexError, ValueError):
                logger.warning(f"Could not format quarter string: {quarter_str}")
                return quarter_str
        
        # Start with the template text
        result = template_text
        
        # Substitute context variables with special handling for current_quarter
        context_vars = {
            'current_quarter': context.current_quarter,
            'market': context.market_name,
            'number_of_years': str(context.number_of_years)
        }
        
        for var_name, var_value in context_vars.items():
            placeholder = f'[{var_name}]'
            if placeholder in result:
                # Special formatting for current_quarter
                if var_name == 'current_quarter':
                    formatted_value = _format_quarter_for_display(var_value)
                else:
                    formatted_value = str(var_value)
                    
                result = result.replace(placeholder, formatted_value)
                logger.debug(f"Substituted {placeholder} with {formatted_value}")
        
        # Substitute metrics variables from calculated_metrics if available
        if 'calculated_metrics' in metrics_data:
            calc_metrics = metrics_data['calculated_metrics']
            for var_name, var_value in calc_metrics.items():
                placeholder = f'[{var_name}]'
                if placeholder in result:
                    # Special handling for current_quarter in calculated metrics too
                    if var_name == 'current_quarter':
                        formatted_value = _format_quarter_for_display(str(var_value))
                    else:
                        # Format the value based on the variable name suffix
                        formatted_value = format_metric_value(var_name, var_value)
                    
                    result = result.replace(placeholder, formatted_value)
                    logger.debug(f"Substituted {placeholder} with {formatted_value} (formatted from {var_value})")
        
        # Check for any remaining unsubstituted variables
        import re
        remaining_vars = re.findall(r'\[([^\]]+)\]', result)
        if remaining_vars:
            logger.warning(f"Unsubstituted variables found: {remaining_vars}")
        
        return result


class NarrativeEngine:
    """Main narrative engine that combines templates and metrics to generate text."""
    
    def __init__(self, template_path: str):
        """
        Initialize the narrative engine.
        
        Args:
            template_path: Path to the YAML template file
        """
        if template_path is None:
            template_path = "text_generation_template.yaml" 
        self.template_loader = TemplateLoader(template_path)
        self.text_selector = TextSelector()
        self.variable_substituter = VariableSubstituter()
        
    def generate_metric_text(
    self, 
    paragraph_key: str,
    metric_key: str, 
    metrics_data: dict[str, Any], 
    context: TemplateContext
    ) -> dict[str, str]:
        """
        Generate text for a single metric using the template.
        
        Args:
            paragraph_key: Paragraph section key (e.g., "overview", "office_metrics")
            metric_key: Metric key (e.g., "total_availability_rate")
            metrics_data: Complete metrics data dictionary
            context: Template context
            
        Returns:
            dict: Dictionary with text components (core_text, qoq_text, yoy_text, historical_text)
        """

        template = self.template_loader.load_template()
        
        # Get the metric template section
        if paragraph_key not in template:
            logger.warning(f"Paragraph key '{paragraph_key}' not found in template")
            return {}
            
        if metric_key not in template[paragraph_key]:
            logger.warning(f"Metric key '{metric_key}' not found in template[{paragraph_key}]")
            return {}
            
        metric_template = template[paragraph_key][metric_key]
        
        # Get the metric data for direction determination
        if metric_key not in metrics_data:
            logger.warning(f"Metric data for '{metric_key}' not found")
            return {}
            
        metric_info = metrics_data[metric_key]
        
        # Prepare the complete metrics data including calculated values for substitution
        complete_metrics = {'calculated_metrics': {}}
        
        # Add basic context variables
        complete_metrics['calculated_metrics'].update({
            'current_quarter': context.current_quarter,
            'market': context.market_name,
            'number_of_years': str(context.number_of_years)
        })
        
        # Add metric-specific calculated values if available
        if 'calculated_metrics' in metrics_data:
            complete_metrics['calculated_metrics'].update(metrics_data['calculated_metrics'])
        
        # Generate text for each component
        result = {}
        
        for component in ['core_text', 'qoq_text', 'yoy_text', 'historical_text']:
            if component not in metric_template:
                result[component] = ""
                continue
                
            # Determine direction based on component
            if component == 'core_text':
                direction = metric_info.get('direction', 'none')
            elif component == 'qoq_text':
                direction = metric_info.get('qoq', {}).get('direction', 'none')
            elif component == 'yoy_text':
                direction = metric_info.get('yoy', {}).get('direction', 'none')
            elif component == 'historical_text':
                direction = metric_info.get('historical', {}).get('direction', 'none')
            else:
                direction = 'none'
            
            # For office properties, generate multiple sentences (office + class_a + class_b)
            if context.property_type.lower() == "office":
                sentences = []
                template_section = metric_template[component]
                
                # 1. Get overall office text
                office_context = TemplateContext(
                    property_type=context.property_type,
                    office_class=None,  # No class for overall office text
                    current_quarter=context.current_quarter,
                    market_name=context.market_name,
                    number_of_years=context.number_of_years
                )
                
                office_text = self.text_selector.select_text(
                    template_section, 
                    office_context, 
                    direction
                )
                if office_text:
                    office_final = self.variable_substituter.substitute_variables(
                        office_text, 
                        complete_metrics, 
                        office_context
                    )
                    sentences.append(office_final)
                
                # 2. Get Class A text (if available in template)
                if ("office" in template_section and 
                    isinstance(template_section["office"], dict) and 
                    "class_a" in template_section["office"]):
                    
                    # Create context for Class A
                    class_a_context = TemplateContext(
                        property_type=context.property_type,
                        office_class="class_a",
                        current_quarter=context.current_quarter,
                        market_name=context.market_name,
                        number_of_years=context.number_of_years
                    )
                    
                    # Get Class A direction (try class-specific first, fallback to overall)
                    class_a_direction = direction
                    if 'class_a' in metric_info:
                        if component == 'core_text':
                            class_a_direction = metric_info['class_a'].get('direction', direction)
                        elif component == 'qoq_text':
                            class_a_direction = metric_info['class_a'].get('qoq', {}).get('direction', direction)
                        elif component == 'yoy_text':
                            class_a_direction = metric_info['class_a'].get('yoy', {}).get('direction', direction)
                        elif component == 'historical_text':
                            class_a_direction = metric_info['class_a'].get('historical', {}).get('direction', direction)
                    
                    class_a_text = self.text_selector.select_text(
                        template_section, 
                        class_a_context, 
                        class_a_direction
                    )
                    if class_a_text:
                        class_a_final = self.variable_substituter.substitute_variables(
                            class_a_text, 
                            complete_metrics, 
                            class_a_context
                        )
                        sentences.append(class_a_final)
                
                # 3. Get Class B text (if available in template)
                if ("office" in template_section and 
                    isinstance(template_section["office"], dict) and 
                    "class_b" in template_section["office"]):
                    
                    # Create context for Class B
                    class_b_context = TemplateContext(
                        property_type=context.property_type,
                        office_class="class_b",
                        current_quarter=context.current_quarter,
                        market_name=context.market_name,
                        number_of_years=context.number_of_years
                    )
                    
                    # Get Class B direction (try class-specific first, fallback to overall)
                    class_b_direction = direction
                    if 'class_b' in metric_info:
                        if component == 'core_text':
                            class_b_direction = metric_info['class_b'].get('direction', direction)
                        elif component == 'qoq_text':
                            class_b_direction = metric_info['class_b'].get('qoq', {}).get('direction', direction)
                        elif component == 'yoy_text':
                            class_b_direction = metric_info['class_b'].get('yoy', {}).get('direction', direction)
                        elif component == 'historical_text':
                            class_b_direction = metric_info['class_b'].get('historical', {}).get('direction', direction)
                    
                    class_b_text = self.text_selector.select_text(
                        template_section, 
                        class_b_context, 
                        class_b_direction
                    )
                    if class_b_text:
                        class_b_final = self.variable_substituter.substitute_variables(
                            class_b_text, 
                            complete_metrics, 
                            class_b_context
                        )
                        sentences.append(class_b_final)
                
                # Combine all sentences for this component
                result[component] = ''.join(sentences)
                
            else:
                # For non-office properties (industrial, all), use existing single-sentence logic
                template_text = self.text_selector.select_text(
                    metric_template[component], 
                    context, 
                    direction
                )
                
                # Substitute variables
                final_text = self.variable_substituter.substitute_variables(
                    template_text, 
                    complete_metrics, 
                    context
                )
                
                result[component] = final_text
            
        return result
    
    def generate_paragraph_text(
        self, 
        paragraph_key: str, 
        metrics_data: dict[str, Any], 
        context: TemplateContext,
        metric_keys: list[str] | None = None
    ) -> str:
        """
        Generate text for an entire paragraph section.
        
        Args:
            paragraph_key: Paragraph section key (e.g., "overview")
            metrics_data: Complete metrics data dictionary
            context: Template context
            metric_keys: Optional list of specific metrics to include
            
        Returns:
            str: Complete paragraph text
        """
        template = self.template_loader.load_template()
        
        if paragraph_key not in template:
            raise ValueError("Paragraph key not found in template")
            
        paragraph_template = template[paragraph_key]
        
        # Determine which metrics to process
        if metric_keys is None:
            metric_keys = list(paragraph_template.keys())
        
        paragraph_sentences = []
        
        for metric_key in metric_keys:
            if metric_key not in paragraph_template:
                logger.warning(f"Metric '{metric_key}' not found in paragraph '{paragraph_key}'")
                continue
                
            # Generate text components for this metric
            metric_text = self.generate_metric_text(
                paragraph_key, 
                metric_key, 
                metrics_data, 
                context
            )
            
            # Combine components into a sentence
            sentence_parts = [
                metric_text.get('core_text', ''),
                metric_text.get('qoq_text', ''),
                metric_text.get('yoy_text', ''),
                metric_text.get('historical_text', '')
            ]
            
            sentence = ''.join(part for part in sentence_parts if part.strip())
            
            if sentence.strip():
                paragraph_sentences.append(sentence.strip())
        
        return ' '.join(paragraph_sentences)
    
    def generate_full_narrative(
        self, 
        metrics_data: dict[str, Any], 
        context: TemplateContext,
        paragraph_keys: list[str] | None = None
    ) -> dict[str, str]:
        """
        Generate the complete narrative for all specified paragraphs.
        
        Args:
            metrics_data: Complete metrics data dictionary
            context: Template context
            paragraph_keys: Optional list of specific paragraphs to include
            
        Returns:
            dict: Dictionary mapping paragraph keys to generated text
        """
        template = self.template_loader.load_template()
        
        # Determine which paragraphs to process
        if paragraph_keys is None:
            paragraph_keys = list(template.keys())
        
        narrative = {}
        
        for paragraph_key in paragraph_keys:
            paragraph_text = self.generate_paragraph_text(
                paragraph_key, 
                metrics_data, 
                context
            )
            narrative[paragraph_key] = paragraph_text
            
        return narrative




def create_narrative_engine(template_path: str | None = None) -> NarrativeEngine:
    """
    Factory function to create a narrative engine with default template path.
    """
    if template_path is None:
        template_path = os.path.join(os.path.dirname(__file__), "text_generation_template.yaml")
    return NarrativeEngine(str(template_path))
