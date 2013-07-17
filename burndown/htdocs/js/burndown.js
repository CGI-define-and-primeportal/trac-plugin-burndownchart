$(document).ready(function(){

  // Expects date as a string in yyyy-mm-dd format, with a time added for 
  // greater accuracy.
  window.addTime = function(date){
    var formatted_date = date + ' 12:01AM'
    return formatted_date
  };

  window.burndownChartData = new Array();
  for (i in burndowndata) {
    if (i == 'name') {
      var milestone_name = burndowndata['name'];
    }
    else if (i == 'start_date') {
      var milestone_start = burndowndata['start_date'];
    }
    else if (i == 'end_date') {
      var milestone_end = burndowndata['end_date'];
    }
    else if (i == 'total_hours') {
      var total_hours = burndowndata['total_hours'];
    }
    else if (i == 'hours_logged') {
      var hours_logged = burndowndata['hours_logged'];
    }
    else if (i == 'effort_units') {
      var effort_units = burndowndata['effort_units']
    }
    else {
      burndownChartData.push(addTime(burndowndata[i]));
    }
  }

  var sortedData = burndownChartData.sort() // To be chronological

  // Team Effort Data
  window.teamEffort = new Array();
  for (i in teameffortdata) {
    teamEffort.push([addTime(i), teameffortdata[i]])
  }

  // Ideal Curve Data
  window.idealCurve = new Array();
  for (i in idealcurvedata) {
    idealCurve.push([addTime(i), idealcurvedata[i]])
  }

  // Makes the jqPlot resize when the window dimensions change
  $(window).on('debouncedresize', function() {
        plot1.replot( { resetAxes: true } );
  });

  // Render the jqPlot burn down chart
  var sprintEffort = [[burndowndata['start_date'], total_hours], ['2013-07-15', 10], [burndowndata['end_date'], 0]];
  var plot1 = $.jqplot('chart1', [sprintEffort, teamEffort, idealCurve], {
    axesDefaults: {
      tickRenderer: $.jqplot.CanvasAxisTickRenderer,
      tickOptions: {
        fontFamily: 'Open Sans',
        fontSize: '8pt'
      },
      labelOptions: {
        textColor: '#0066CC',
        fontFamily: 'Open Sans',
        fontSize: '10pt',
        fontWeight: 'normal'
      }
    },
    axes: {
      xaxis: {
        renderer:$.jqplot.DateAxisRenderer,
        tickOptions:{formatString: '%d %b'},
        label: 'Days in Milestone',
        tickInterval:'1 day',
        min: burndowndata['start_date'],
        max: burndowndata['end_date'],
      },
      yaxis: {
        label: 'Effort (' + effort_units +')',
        min: 0,
        labelRenderer: $.jqplot.CanvasAxisLabelRenderer
      }
    }, 
    highlighter: {
      show: true, 
      tooltipAxes: 'both',
      sizeAdjust: 7.5,
      fadeTooltip: true,
      tooltipFadeSpeed: 'fast',
      tooltipAxes: 'xy',
      formatString: '%s - %s ' + effort_units,
      },
    series:[
            {color:'#5FAB78', label: 'Sprint effort'},
            {label: 'Team effort'},
            {label: 'Ideal effort', showMarker: false},
           ],
    legend: {
      show: true,
      }
  });
});